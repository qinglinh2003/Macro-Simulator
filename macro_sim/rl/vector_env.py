"""Process-isolated vector sampling for CPU-bound simulation environments."""
from __future__ import annotations

from collections.abc import Sequence
import math
import multiprocessing as mp
from multiprocessing.connection import Connection
import traceback
from typing import Any

import numpy as np

from .experiment import (
    BatchReset,
    BatchStep,
    EnvironmentFactory,
    SynchronousEnvironmentBatch,
)


class RemoteEnvironmentError(RuntimeError):
    """Raised when an environment worker reports a construction/step failure."""


def _worker(
    connection: Connection,
    serialized_factory: bytes,
    seed: int,
    compact_infos: bool,
) -> None:
    environment = None
    try:
        import cloudpickle

        factory = cloudpickle.loads(serialized_factory)
        current_seed = seed
        environment = factory(current_seed)
        connection.send(("ready", None))
        while True:
            command, payload = connection.recv()
            if command == "reset":
                result = environment.reset(seed=current_seed)
                connection.send(("ok", _compact_result_info(result, compact_infos)))
            elif command == "reseed":
                new_seed = int(payload)
                replacement = factory(new_seed)
                old_environment = environment
                environment = replacement
                current_seed = new_seed
                close = getattr(old_environment, "close", None)
                if callable(close):
                    close()
                result = environment.reset(seed=current_seed)
                connection.send(("ok", _compact_result_info(result, compact_infos)))
            elif command == "step":
                result = environment.step(payload)
                connection.send(("ok", _compact_result_info(result, compact_infos)))
            elif command == "close":
                connection.send(("ok", None))
                return
            else:
                raise RuntimeError(f"unknown worker command {command!r}")
    except (EOFError, BrokenPipeError):
        return
    except BaseException as exc:  # propagate type/message/trace without pickling exc
        try:
            connection.send((
                "error",
                {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            ))
        except (EOFError, BrokenPipeError):
            pass
    finally:
        if environment is not None:
            close = getattr(environment, "close", None)
            if callable(close):
                close()
        connection.close()


_TRAINING_INFO_KEYS = frozenset({
    "action_mask",
    "elapsed_ticks",
    "reward_time_normalization",
})


def _compact_result_info(result: Any, enabled: bool) -> Any:
    """Drop frontend/debug payloads before worker IPC on trainer-only batches."""
    if not enabled:
        return result
    if not isinstance(result, tuple) or len(result) not in {2, 5}:
        raise TypeError("environment reset/step returned an incompatible result")
    info = result[-1]
    if not isinstance(info, dict):
        try:
            info = dict(info)
        except (TypeError, ValueError) as exc:
            raise TypeError("environment info must be a mapping") from exc
    compact = {key: info[key] for key in _TRAINING_INFO_KEYS if key in info}
    return (*result[:-1], compact)


class SubprocessEnvironmentBatch:
    """One persistent environment per worker with batched parent-side arrays.

    There is deliberately no implicit auto-reset: terminal observations remain
    available for correct time-limit bootstrapping, and the trainer explicitly
    controls episode/seed boundaries.
    """

    def __init__(
        self,
        factory: EnvironmentFactory,
        seeds: Sequence[int],
        *,
        start_method: str = "spawn",
        timeout_seconds: float = 300.0,
        compact_infos: bool = False,
    ) -> None:
        if not callable(factory):
            raise TypeError("environment factory must be callable")
        try:
            checked_seeds = tuple(seeds)
        except TypeError as exc:
            raise TypeError("seeds must be a non-empty sequence") from exc
        if not checked_seeds:
            raise ValueError("seeds must be a non-empty sequence")
        if any(
            isinstance(seed, bool) or not isinstance(seed, (int, np.integer))
            or not 0 <= int(seed) < 2**63
            for seed in checked_seeds
        ):
            raise ValueError("seeds must contain integers in [0, 2**63)")
        self.seeds = tuple(int(seed) for seed in checked_seeds)
        if not isinstance(start_method, str):
            raise TypeError("start_method must be a multiprocessing method name")
        if start_method not in mp.get_all_start_methods():
            raise ValueError(
                f"unsupported multiprocessing start method {start_method!r}"
            )
        if isinstance(timeout_seconds, bool) or not isinstance(
            timeout_seconds, (int, float),
        ) or not math.isfinite(float(timeout_seconds)) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive finite number")
        self.timeout_seconds = float(timeout_seconds)
        if not isinstance(compact_infos, bool):
            raise TypeError("compact_infos must be a boolean")
        self.compact_infos = compact_infos
        try:
            import cloudpickle
        except ImportError as exc:  # supplied by the Gymnasium/RL extra
            raise ModuleNotFoundError(
                "cloudpickle is required for subprocess RL environments"
            ) from exc
        serialized_factory = cloudpickle.dumps(factory, protocol=5)
        context = mp.get_context(start_method)
        parents: list[Connection] = []
        processes: list[mp.Process] = []
        try:
            for index, seed in enumerate(self.seeds):
                parent, child = context.Pipe(duplex=True)
                process = context.Process(
                    target=_worker,
                    args=(child, serialized_factory, seed, compact_infos),
                    name=f"macro-sim-rl-{index}",
                    daemon=True,
                )
                process.start()
                child.close()
                parents.append(parent)
                processes.append(process)
            self._connections = tuple(parents)
            self._processes = tuple(processes)
            self._closed = False
            self._ready = False
            self._ended = False
            for connection, process in zip(
                self._connections, self._processes, strict=True,
            ):
                status, payload = self._receive(connection, process)
                if status != "ready":
                    self._raise_remote(payload)
        except Exception:
            for connection in parents:
                connection.close()
            for process in processes:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5.0)
            raise

    @property
    def num_envs(self) -> int:
        return len(self.seeds)

    @staticmethod
    def _raise_remote(payload: Any) -> None:
        if isinstance(payload, dict):
            raise RemoteEnvironmentError(
                f"worker {payload.get('type', 'error')}: "
                f"{payload.get('message', '')}\n{payload.get('traceback', '')}"
            )
        raise RemoteEnvironmentError(f"environment worker failed: {payload!r}")

    def _receive_all(self) -> list[Any]:
        values: list[Any] = []
        for connection, process in zip(
            self._connections, self._processes, strict=True,
        ):
            status, payload = self._receive(connection, process)
            if status != "ok":
                self._ready = False
                self._raise_remote(payload)
            values.append(payload)
        return values

    def _receive(self, connection: Connection, process: mp.Process):
        if not connection.poll(self.timeout_seconds):
            state = (
                f"exitcode={process.exitcode}"
                if not process.is_alive() else "still alive"
            )
            raise RemoteEnvironmentError(
                "environment worker timed out after "
                f"{self.timeout_seconds:g}s ({state})"
            )
        try:
            return connection.recv()
        except EOFError as exc:
            raise RemoteEnvironmentError(
                f"environment worker exited without a response "
                f"(exitcode={process.exitcode})"
            ) from exc

    def reset(self) -> BatchReset:
        if self._closed:
            raise RuntimeError("subprocess environment batch is closed")
        for connection in self._connections:
            connection.send(("reset", None))
        values = self._receive_all()
        observations, infos = zip(*values, strict=True)
        stacked = SynchronousEnvironmentBatch._stack(observations)
        masks = SynchronousEnvironmentBatch._stack_action_masks(infos)
        self._ready = True
        self._ended = False
        return BatchReset(stacked, masks, tuple(infos))

    def reseed(self, seeds: Sequence[int]) -> BatchReset:
        """Rebuild worker-local environments without respawning processes."""
        if self._closed:
            raise RuntimeError("subprocess environment batch is closed")
        try:
            checked = tuple(seeds)
        except TypeError as exc:
            raise TypeError("seeds must be a sequence") from exc
        if len(checked) != self.num_envs or any(
            isinstance(seed, bool) or not isinstance(seed, (int, np.integer))
            or not 0 <= int(seed) < 2**63
            for seed in checked
        ):
            raise ValueError(
                "seeds must contain one integer in [0, 2**63) per worker"
            )
        checked = tuple(int(seed) for seed in checked)
        for connection, seed in zip(self._connections, checked, strict=True):
            connection.send(("reseed", seed))
        values = self._receive_all()
        observations, infos = zip(*values, strict=True)
        stacked = SynchronousEnvironmentBatch._stack(observations)
        masks = SynchronousEnvironmentBatch._stack_action_masks(infos)
        self.seeds = checked
        self._ready = True
        self._ended = False
        return BatchReset(stacked, masks, tuple(infos))

    def step(self, actions: Sequence[Any]) -> BatchStep:
        if self._closed:
            raise RuntimeError("subprocess environment batch is closed")
        if not self._ready:
            raise RuntimeError("reset() must be called before step()")
        if self._ended:
            raise RuntimeError("a batch slot ended; reset() before the next step")
        if len(actions) != self.num_envs:
            raise ValueError("actions length must equal num_envs")
        for connection, action in zip(self._connections, actions, strict=True):
            connection.send(("step", action))
        try:
            values = self._receive_all()
            observations: list[Any] = []
            rewards = np.empty(self.num_envs, dtype=np.float64)
            elapsed_ticks = np.empty(self.num_envs, dtype=np.int64)
            terminated = np.empty(self.num_envs, dtype=np.bool_)
            truncated = np.empty(self.num_envs, dtype=np.bool_)
            infos = []
            for index, value in enumerate(values):
                observation, reward, term, trunc, info = value
                if isinstance(reward, bool) or not isinstance(
                    reward, (int, float, np.number),
                ) or not math.isfinite(float(reward)):
                    raise ValueError("environment reward must be finite")
                elapsed = info.get("elapsed_ticks")
                if isinstance(elapsed, bool) or not isinstance(
                    elapsed, (int, np.integer),
                ) or int(elapsed) < 1:
                    raise ValueError(
                        "environment info.elapsed_ticks must be a positive integer"
                    )
                observations.append(observation)
                rewards[index] = float(reward)
                elapsed_ticks[index] = int(elapsed)
                terminated[index] = bool(term)
                truncated[index] = bool(trunc)
                infos.append(info)
            stacked = SynchronousEnvironmentBatch._stack(observations)
            masks = SynchronousEnvironmentBatch._stack_action_masks(infos)
        except Exception:
            self._ready = False
            raise
        self._ended = bool(np.any(terminated | truncated))
        return BatchStep(
            stacked,
            masks,
            rewards,
            elapsed_ticks,
            terminated,
            truncated,
            tuple(infos),
        )

    def close(self) -> None:
        if getattr(self, "_closed", True):
            return
        self._closed = True
        for connection, process in zip(
            self._connections, self._processes, strict=True,
        ):
            if process.is_alive():
                try:
                    connection.send(("close", None))
                except (EOFError, BrokenPipeError):
                    pass
        for connection, process in zip(
            self._connections, self._processes, strict=True,
        ):
            if process.is_alive():
                try:
                    connection.poll(1.0) and connection.recv()
                except (EOFError, BrokenPipeError):
                    pass
            connection.close()
            process.join(timeout=5.0)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5.0)

    def __enter__(self) -> "SubprocessEnvironmentBatch":
        return self

    def __exit__(self, exc_type, exc, traceback_value) -> None:
        self.close()
