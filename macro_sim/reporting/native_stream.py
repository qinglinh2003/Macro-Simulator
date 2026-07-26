"""Bounded-memory columnar stream for committed native M10 metric frames."""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
import os
from pathlib import Path
import struct
from typing import Any


STREAM_FORMAT = "macro-sim-native-metric-stream-v1"
CHUNK_MAGIC = b"MSM10H1\0"
CHUNK_VERSION = 1
_HEADER = struct.Struct("<8sIQQII32s")


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=True, allow_nan=False,
            separators=(",", ":"), sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _contract(root: Path) -> tuple[tuple[str, ...], str]:
    path = root / "schemas/m10/maintained_metrics.json"
    payload = path.read_bytes()
    document = json.loads(payload)
    if document.get("schema_version") != "m10-maintained-metrics-v1":
        raise ValueError("unsupported M10 maintained metric contract")
    identifiers = tuple(item["id"] for item in document["metrics"])
    if not identifiers or len(identifiers) != len(set(identifiers)):
        raise ValueError("M10 maintained metric contract IDs are invalid")
    return identifiers, hashlib.sha256(payload).hexdigest()


class NativeMetricStream:
    """Append immutable metric chunks while retaining only one chunk in memory."""

    def __init__(
        self, directory: str | Path, *, chunk_frames: int = 128,
        start_sequence: int = 0,
    ) -> None:
        if isinstance(chunk_frames, bool) or not isinstance(chunk_frames, int):
            raise TypeError("chunk_frames must be an integer")
        if not 1 <= chunk_frames <= 4096:
            raise ValueError("chunk_frames must be between 1 and 4096")
        if isinstance(start_sequence, bool) or not isinstance(
            start_sequence, int,
        ):
            raise TypeError("start_sequence must be an integer")
        if start_sequence < 0:
            raise ValueError("start_sequence cannot be negative")
        self.directory = Path(directory).resolve()
        self.chunk_directory = self.directory / "chunks"
        self.manifest_path = self.directory / "manifest.json"
        self.chunk_frames = chunk_frames
        root = Path(__file__).resolve().parents[2]
        self.metric_ids, self.contract_sha256 = _contract(root)
        self._buffer: list[tuple[int, dict[str, Any]]] = []
        self.directory.mkdir(parents=True, exist_ok=True)
        self.chunk_directory.mkdir(parents=True, exist_ok=True)
        if self.manifest_path.is_file():
            self._manifest = self._load_manifest()
            if self._manifest["chunk_frames"] != chunk_frames:
                raise ValueError("metric stream chunk width does not match")
        else:
            self._manifest = {
                "chunk_frames": chunk_frames,
                "chunks": [],
                "contract_sha256": self.contract_sha256,
                "first_sequence": start_sequence,
                "format": STREAM_FORMAT,
                "metric_count": len(self.metric_ids),
                "next_sequence": start_sequence,
            }
            self._write_manifest()

    @property
    def next_sequence(self) -> int:
        return int(self._manifest["next_sequence"]) + len(self._buffer)

    @property
    def pending_frames(self) -> int:
        return len(self._buffer)

    @property
    def retained_buffer_bytes(self) -> int:
        if not self._buffer:
            return 0
        economy_count = int(self._buffer[0][1]["economy_count"])
        return (
            len(self._buffer) * economy_count * len(self.metric_ids) * 9
        )

    def _load_manifest(self) -> dict[str, Any]:
        try:
            raw = self.manifest_path.read_bytes()
            document = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("metric stream manifest is unreadable") from exc
        expected_fields = {
            "chunk_frames", "chunks", "contract_sha256", "first_sequence",
            "format", "metric_count", "next_sequence",
        }
        if not isinstance(document, dict) or set(document) != expected_fields:
            raise ValueError("metric stream manifest fields are invalid")
        if document["format"] != STREAM_FORMAT:
            raise ValueError("metric stream format is unsupported")
        if document["contract_sha256"] != self.contract_sha256:
            raise ValueError("metric stream contract hash does not match")
        if document["metric_count"] != len(self.metric_ids):
            raise ValueError("metric stream metric width does not match")
        if _canonical_json(document) != raw:
            raise ValueError("metric stream manifest is not canonical")
        cursor = int(document["first_sequence"])
        previous_tick = -1
        for chunk in document["chunks"]:
            if set(chunk) != {
                "byte_count", "economy_count", "first_sequence",
                "frame_count", "last_tick", "sha256",
            }:
                raise ValueError("metric stream chunk metadata is invalid")
            if int(chunk["first_sequence"]) != cursor:
                raise ValueError("metric stream chunks are not contiguous")
            digest = str(chunk["sha256"])
            path = self.chunk_directory / f"{digest}.bin"
            payload = path.read_bytes()
            if (
                len(payload) != int(chunk["byte_count"])
                or hashlib.sha256(payload).hexdigest() != digest
            ):
                raise ValueError("metric stream chunk content is corrupt")
            previous_tick = self._validate_chunk_payload(
                payload, chunk, cursor, previous_tick,
            )
            cursor += int(chunk["frame_count"])
        if cursor != int(document["next_sequence"]):
            raise ValueError("metric stream manifest cursor is invalid")
        return document

    def _validate_chunk_payload(
        self, payload: bytes, metadata: Mapping[str, Any],
        expected_sequence: int, previous_tick: int,
    ) -> int:
        if len(payload) < _HEADER.size:
            raise ValueError("metric stream chunk header is truncated")
        (
            magic, version, first_sequence, frame_count, economy_count,
            metric_count, contract_hash,
        ) = _HEADER.unpack_from(payload)
        if (
            magic != CHUNK_MAGIC
            or version != CHUNK_VERSION
            or first_sequence != expected_sequence
            or first_sequence != int(metadata["first_sequence"])
            or frame_count != int(metadata["frame_count"])
            or economy_count != int(metadata["economy_count"])
            or metric_count != len(self.metric_ids)
            or contract_hash.hex() != self.contract_sha256
            or frame_count <= 0
            or economy_count <= 0
        ):
            raise ValueError("metric stream chunk header is invalid")
        cell_count = frame_count * economy_count * metric_count
        expected_bytes = _HEADER.size + frame_count * 8 + cell_count * 9
        if len(payload) != expected_bytes:
            raise ValueError("metric stream chunk dimensions are invalid")
        ticks = struct.unpack_from(
            f"<{frame_count}Q", payload, _HEADER.size,
        )
        if (
            any(right <= left for left, right in zip(ticks, ticks[1:]))
            or ticks[0] <= previous_tick
            or ticks[-1] != int(metadata["last_tick"])
        ):
            raise ValueError("metric stream chunk ticks are invalid")
        validity_start = _HEADER.size + frame_count * 8
        validity_end = validity_start + cell_count
        view = memoryview(payload)
        if any(
            value not in (0, 1)
            for value in view[validity_start:validity_end]
        ):
            raise ValueError("metric stream chunk validity bitmap is invalid")
        for (value,) in struct.iter_unpack("<d", view[validity_end:]):
            if not math.isfinite(value):
                raise ValueError("metric stream chunk contains non-finite data")
        return int(ticks[-1])

    def _write_manifest(self) -> None:
        payload = _canonical_json(self._manifest)
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, self.manifest_path)

    def _validated_frame(self, frame: Mapping[str, Any]) -> dict[str, Any]:
        if set(frame) != {"economies", "economy_count", "tick"}:
            raise ValueError("native metric frame fields are invalid")
        economy_count = int(frame["economy_count"])
        economies = list(frame["economies"])
        if economy_count <= 0 or len(economies) != economy_count:
            raise ValueError("native metric frame economy width is invalid")
        rows: list[dict[str, float | None]] = []
        expected = set(self.metric_ids)
        for row in economies:
            if not isinstance(row, Mapping) or set(row) != expected:
                raise ValueError("native metric frame metric IDs are invalid")
            checked: dict[str, float | None] = {}
            for metric_id in self.metric_ids:
                value = row[metric_id]
                if value is None:
                    checked[metric_id] = None
                    continue
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError("native metric frame contains non-finite data")
                checked[metric_id] = number
            rows.append(checked)
        return {
            "tick": int(frame["tick"]),
            "economy_count": economy_count,
            "economies": rows,
        }

    def sync(self, session: Any) -> int:
        """Drain all newly retained frames or fail before a history gap."""
        bounds = session.history_bounds()
        cursor = self.next_sequence
        oldest = int(bounds["oldest_sequence"])
        newest = int(bounds["next_sequence"])
        if cursor < oldest:
            raise RuntimeError(
                "metric stream cursor fell behind the native history ring"
            )
        if cursor > newest:
            raise RuntimeError(
                "metric stream cursor is ahead of the native history ring"
            )
        appended = 0
        while cursor < newest:
            page = session.maintained_history_page(
                cursor, min(self.chunk_frames, newest - cursor),
            )
            if int(page["first_sequence"]) != cursor:
                raise RuntimeError("native history page cursor changed")
            frames = list(page["frames"])
            page_next = int(page["next_sequence"])
            if not frames or page_next != cursor + len(frames):
                raise RuntimeError("native history page is not contiguous")
            for sequence, frame in enumerate(frames, start=cursor):
                self._buffer.append(
                    (sequence, self._validated_frame(frame))
                )
                appended += 1
                if len(self._buffer) == self.chunk_frames:
                    self.flush()
            cursor = page_next
        return appended

    def _encode_buffer(self) -> tuple[bytes, int, int]:
        if not self._buffer:
            raise RuntimeError("cannot encode an empty metric stream chunk")
        first_sequence = self._buffer[0][0]
        for offset, (sequence, _) in enumerate(self._buffer):
            if sequence != first_sequence + offset:
                raise RuntimeError("metric stream buffer is not contiguous")
        frames = [frame for _, frame in self._buffer]
        economy_count = int(frames[0]["economy_count"])
        if any(
            int(frame["economy_count"]) != economy_count
            for frame in frames
        ):
            raise RuntimeError("metric stream economy width changed in a chunk")
        payload = bytearray(_HEADER.pack(
            CHUNK_MAGIC,
            CHUNK_VERSION,
            first_sequence,
            len(frames),
            economy_count,
            len(self.metric_ids),
            bytes.fromhex(self.contract_sha256),
        ))
        payload.extend(struct.pack(
            f"<{len(frames)}Q",
            *(int(frame["tick"]) for frame in frames),
        ))
        valid = bytearray()
        values: list[float] = []
        for economy in range(economy_count):
            for metric_id in self.metric_ids:
                for frame in frames:
                    value = frame["economies"][economy][metric_id]
                    valid.append(0 if value is None else 1)
                    values.append(0.0 if value is None else float(value))
        payload.extend(valid)
        payload.extend(struct.pack(f"<{len(values)}d", *values))
        return bytes(payload), first_sequence, economy_count

    def flush(self) -> str | None:
        """Write the pending chunk and atomically advance its manifest."""
        if not self._buffer:
            return None
        payload, first_sequence, economy_count = self._encode_buffer()
        digest = hashlib.sha256(payload).hexdigest()
        destination = self.chunk_directory / f"{digest}.bin"
        if not destination.is_file():
            temporary = self.chunk_directory / f".{digest}.tmp"
            temporary.write_bytes(payload)
            os.replace(temporary, destination)
        frame_count = len(self._buffer)
        self._manifest["chunks"].append({
            "byte_count": len(payload),
            "economy_count": economy_count,
            "first_sequence": first_sequence,
            "frame_count": frame_count,
            "last_tick": int(self._buffer[-1][1]["tick"]),
            "sha256": digest,
        })
        self._manifest["next_sequence"] = first_sequence + frame_count
        self._buffer.clear()
        self._write_manifest()
        return digest

    def close(self) -> None:
        self.flush()
