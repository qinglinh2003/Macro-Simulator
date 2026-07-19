"""Safe, portable artifact I/O for deployed RL policies.

Artifacts are ZIP containers with exactly two members:

``manifest.json``
    Canonical JSON containing versioned codec/model schemas and hashes.
``weights.npz``
    Numeric-only NumPy arrays loaded with ``allow_pickle=False``.

Unlike engine checkpoints, this format never deserializes Python objects and is
appropriate for moving a trained policy between trusted or untrusted machines.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any
import zipfile

import numpy as np

from macro_sim.controllers.protocol import (
    canonical_json,
    canonical_value,
    immutable_json_mapping,
)

from .codec import ContextCodec, DirectionalActionCodec
from .model import NumpyMLPPolicy, SUPPORTED_DTYPES


ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_FORMAT = "macro_sim_rl_policy_v1"
MANIFEST_NAME = "manifest.json"
WEIGHTS_NAME = "weights.npz"
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_WEIGHTS_BYTES = 1024 * 1024 * 1024
MAX_PARAMETER_BYTES = 512 * 1024 * 1024
MAX_TOTAL_PARAMETER_BYTES = 1024 * 1024 * 1024


class ArtifactError(ValueError):
    """A model artifact failed structural, integrity, or numeric validation."""


@dataclass(frozen=True)
class LoadedArtifact:
    """Validated policy plus provenance needed by held-out evaluation."""

    policy: NumpyMLPPolicy
    metadata: Mapping[str, Any]
    artifact_sha256: str
    context_contract_hash: str
    action_contract_hash: str
    model_contract_hash: str


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_json_loads(value: bytes) -> Any:
    if len(value) > MAX_MANIFEST_BYTES:
        raise ArtifactError("artifact manifest exceeds the size limit")

    def reject_constant(token: str) -> None:
        raise ArtifactError(f"artifact JSON contains forbidden constant {token}")

    def unique_object(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ArtifactError(f"artifact JSON contains duplicate key {key!r}")
            result[key] = item
        return result

    try:
        return json.loads(
            value.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        )
    except UnicodeDecodeError as exc:
        raise ArtifactError("artifact manifest is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ArtifactError("artifact manifest is not valid JSON") from exc


def _exact_keys(value: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ArtifactError(
            f"{where} keys differ; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _zip_member(name: str, *, compression: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = compression
    info.create_system = 3
    info.external_attr = 0o100600 << 16
    return info


def _parameter_specs(model_spec: Mapping[str, Any]) -> dict[str, tuple[np.dtype, tuple[int, ...]]]:
    raw = model_spec.get("parameter_specs")
    if not isinstance(raw, Mapping):
        raise ArtifactError("model parameter_specs must be a mapping")
    result: dict[str, tuple[np.dtype, tuple[int, ...]]] = {}
    total_bytes = 0
    for name, spec in raw.items():
        if not isinstance(name, str) or not name:
            raise ArtifactError("model parameter name must be a non-empty string")
        if not isinstance(spec, Mapping):
            raise ArtifactError(f"parameter spec for {name!r} must be a mapping")
        _exact_keys(spec, {"dtype", "shape"}, f"parameter spec {name!r}")
        dtype_name = spec["dtype"]
        if dtype_name not in SUPPORTED_DTYPES:
            raise ArtifactError(f"unsupported parameter dtype {dtype_name!r}")
        raw_shape = spec["shape"]
        if not isinstance(raw_shape, list):
            raise ArtifactError(f"parameter shape for {name!r} must be a list")
        shape: list[int] = []
        elements = 1
        for dimension in raw_shape:
            if isinstance(dimension, bool) or not isinstance(dimension, int) \
                    or dimension < 0:
                raise ArtifactError(f"parameter shape for {name!r} is invalid")
            shape.append(dimension)
            elements *= dimension
            if elements * np.dtype(dtype_name).itemsize > MAX_PARAMETER_BYTES:
                raise ArtifactError(f"parameter {name!r} exceeds the size limit")
        byte_count = elements * np.dtype(dtype_name).itemsize
        total_bytes += byte_count
        if total_bytes > MAX_TOTAL_PARAMETER_BYTES:
            raise ArtifactError("model parameters exceed the total size limit")
        result[name] = (np.dtype(dtype_name), tuple(shape))
    return result


def _validate_inner_npz(
    payload: bytes,
    expected: Mapping[str, tuple[np.dtype, tuple[int, ...]]],
) -> None:
    """Bound decompression before NumPy allocates any declared arrays."""
    try:
        with zipfile.ZipFile(BytesIO(payload), "r") as archive:
            infos = archive.infolist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArtifactError("weights.npz is not a valid NPZ archive") from exc
    names = [item.filename for item in infos]
    expected_names = {f"{name}.npy" for name in expected}
    if len(names) != len(set(names)):
        raise ArtifactError("weights.npz contains duplicate members")
    if set(names) != expected_names:
        raise ArtifactError("weights.npz parameter members do not match manifest")
    total = 0
    for info in infos:
        if info.flag_bits & 0x1:
            raise ArtifactError("encrypted NPZ members are not supported")
        parameter_name = info.filename[:-4]
        dtype, shape = expected[parameter_name]
        expected_bytes = math.prod(shape) * dtype.itemsize
        # A .npy header for our bounded rank/shape is tiny.  The allowance keeps
        # this check format-compatible without permitting a decompression bomb.
        if info.file_size > expected_bytes + 64 * 1024:
            raise ArtifactError(f"NPZ member {info.filename!r} exceeds expected size")
        total += info.file_size
        if total > MAX_TOTAL_PARAMETER_BYTES + len(infos) * 64 * 1024:
            raise ArtifactError("NPZ uncompressed content exceeds the size limit")


def save_artifact(
    path: str | os.PathLike[str],
    policy: NumpyMLPPolicy,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    """Atomically write a deterministic JSON+NPZ policy artifact."""
    if not isinstance(policy, NumpyMLPPolicy):
        raise TypeError("policy must be a NumpyMLPPolicy")
    target = Path(path)
    if not target.name:
        raise ValueError("artifact path must name a file")
    parent = target.parent
    if not parent.exists() or not parent.is_dir():
        raise FileNotFoundError(f"artifact parent directory does not exist: {parent}")
    if metadata is None:
        metadata_value: dict[str, Any] = {}
    else:
        if not isinstance(metadata, Mapping):
            raise TypeError("artifact metadata must be a mapping")
        normalized = canonical_value(dict(metadata))
        if not isinstance(normalized, dict):
            raise TypeError("artifact metadata must normalize to an object")
        metadata_value = normalized

    arrays = policy.parameter_arrays()
    buffer = BytesIO()
    np.savez_compressed(buffer, **arrays)
    weights = buffer.getvalue()
    if len(weights) > MAX_WEIGHTS_BYTES:
        raise ValueError("serialized model weights exceed the size limit")
    model_spec = policy.model_spec()
    _parameter_specs(model_spec)
    manifest = {
        "action_codec": policy.action_codec.to_dict(),
        "action_contract_hash": policy.action_codec.contract_hash,
        "artifact_format": ARTIFACT_FORMAT,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "context_codec": policy.context_codec.to_dict(),
        "context_contract_hash": policy.context_codec.contract_hash,
        "metadata": metadata_value,
        "model": model_spec,
        "model_contract_hash": _sha256(
            canonical_json(model_spec).encode("utf-8")
        ),
        "weights": {
            "file": WEIGHTS_NAME,
            "sha256": _sha256(weights),
            "size_bytes": len(weights),
        },
    }
    manifest_bytes = canonical_json(manifest).encode("utf-8")
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise ValueError("serialized model manifest exceeds the size limit")

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b", prefix=f".{target.name}.", suffix=".tmp",
            dir=parent, delete=False,
        ) as handle:
            temporary_name = handle.name
            with zipfile.ZipFile(handle, mode="w") as archive:
                archive.writestr(
                    _zip_member(MANIFEST_NAME, compression=zipfile.ZIP_DEFLATED),
                    manifest_bytes,
                )
                # NPZ is already compressed; storing avoids costly double compression.
                archive.writestr(
                    _zip_member(WEIGHTS_NAME, compression=zipfile.ZIP_STORED),
                    weights,
                )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
        temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
    return target


def load_artifact_bundle(
    path: str | os.PathLike[str],
    *,
    deterministic: bool | None = None,
    seed: int | None = None,
) -> LoadedArtifact:
    """Load a policy and immutable provenance without executing code."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"model artifact does not exist: {source}")
    try:
        with zipfile.ZipFile(source, mode="r") as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                raise ArtifactError("model artifact contains duplicate members")
            if set(names) != {MANIFEST_NAME, WEIGHTS_NAME} or len(names) != 2:
                raise ArtifactError(
                    "model artifact must contain exactly manifest.json and weights.npz"
                )
            by_name = {item.filename: item for item in infos}
            if by_name[MANIFEST_NAME].file_size > MAX_MANIFEST_BYTES:
                raise ArtifactError("artifact manifest exceeds the size limit")
            if by_name[WEIGHTS_NAME].file_size > MAX_WEIGHTS_BYTES:
                raise ArtifactError("artifact weights exceed the size limit")
            if any(item.flag_bits & 0x1 for item in infos):
                raise ArtifactError("encrypted artifact members are not supported")
            manifest_bytes = archive.read(MANIFEST_NAME)
            weights_bytes = archive.read(WEIGHTS_NAME)
    except zipfile.BadZipFile as exc:
        raise ArtifactError("model artifact is not a valid ZIP container") from exc

    manifest = _strict_json_loads(manifest_bytes)
    if not isinstance(manifest, Mapping):
        raise ArtifactError("artifact manifest root must be an object")
    _exact_keys(manifest, {
        "action_codec", "action_contract_hash", "artifact_format",
        "artifact_schema_version", "context_codec", "context_contract_hash",
        "metadata", "model", "model_contract_hash", "weights",
    }, "artifact manifest")
    if manifest["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION:
        raise ArtifactError(
            "unsupported artifact schema_version "
            f"{manifest['artifact_schema_version']!r}"
        )
    if manifest["artifact_format"] != ARTIFACT_FORMAT:
        raise ArtifactError(f"unsupported artifact format {manifest['artifact_format']!r}")
    if not isinstance(manifest["metadata"], Mapping):
        raise ArtifactError("artifact metadata must be an object")
    weights_spec = manifest["weights"]
    if not isinstance(weights_spec, Mapping):
        raise ArtifactError("artifact weights spec must be an object")
    _exact_keys(weights_spec, {"file", "sha256", "size_bytes"}, "weights spec")
    if weights_spec["file"] != WEIGHTS_NAME:
        raise ArtifactError("artifact weights file name is unsupported")
    if isinstance(weights_spec["size_bytes"], bool) or not isinstance(
        weights_spec["size_bytes"], int,
    ) or weights_spec["size_bytes"] != len(weights_bytes):
        raise ArtifactError("artifact weights size mismatch")
    if weights_spec["sha256"] != _sha256(weights_bytes):
        raise ArtifactError("artifact weights SHA-256 mismatch")

    try:
        context_codec = ContextCodec.from_dict(manifest["context_codec"])
        if manifest["context_contract_hash"] != context_codec.contract_hash:
            raise ArtifactError("artifact context contract SHA-256 mismatch")
        action_codec = DirectionalActionCodec.from_dict(
            manifest["action_codec"], context_codec=context_codec,
        )
        if manifest["action_contract_hash"] != action_codec.contract_hash:
            raise ArtifactError("artifact action contract SHA-256 mismatch")
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ArtifactError):
            raise
        raise ArtifactError(f"artifact codec validation failed: {exc}") from exc

    model_spec = manifest["model"]
    if not isinstance(model_spec, Mapping):
        raise ArtifactError("artifact model spec must be an object")
    if manifest["model_contract_hash"] != _sha256(
        canonical_json(model_spec).encode("utf-8")
    ):
        raise ArtifactError("artifact model contract SHA-256 mismatch")
    expected_parameters = _parameter_specs(model_spec)
    _validate_inner_npz(weights_bytes, expected_parameters)
    try:
        with np.load(BytesIO(weights_bytes), allow_pickle=False) as archive:
            if set(archive.files) != set(expected_parameters):
                raise ArtifactError("NPZ parameter names do not match manifest")
            arrays = {
                name: np.array(archive[name], copy=True, order="C")
                for name in sorted(expected_parameters)
            }
    except ArtifactError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise ArtifactError(f"artifact numeric payload is invalid: {exc}") from exc

    try:
        policy = NumpyMLPPolicy.from_spec_and_arrays(
            context_codec,
            action_codec,
            model_spec,
            arrays,
            deterministic=deterministic,
            seed=seed,
        )
    except (TypeError, ValueError) as exc:
        raise ArtifactError(f"artifact model validation failed: {exc}") from exc
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return LoadedArtifact(
        policy=policy,
        metadata=immutable_json_mapping(manifest["metadata"]),
        artifact_sha256=digest.hexdigest(),
        context_contract_hash=context_codec.contract_hash,
        action_contract_hash=action_codec.contract_hash,
        model_contract_hash=manifest["model_contract_hash"],
    )


def load_artifact(
    path: str | os.PathLike[str],
    *,
    deterministic: bool | None = None,
    seed: int | None = None,
) -> NumpyMLPPolicy:
    """Load and fully validate an inference policy without executing code."""
    return load_artifact_bundle(
        path, deterministic=deterministic, seed=seed,
    ).policy
