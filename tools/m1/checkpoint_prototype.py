#!/usr/bin/env python3
"""Generate and verify the deterministic M1 checkpoint-envelope prototype."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import statistics
import struct
import sys
import time
from typing import Any

import flatbuffers
from flatbuffers import encode, number_types, packer
from flatbuffers.table import Table

from canonical_encoding import (
    CANONICAL_ENCODING_VERSION,
    CanonicalEncodingError,
    canonical_decode,
    canonical_encode,
)


ROOT = Path(__file__).resolve().parents[2]
VECTOR_OUTPUT = ROOT / "schemas/m1/canonical_encoding_vectors.json"
PROTOTYPE_OUTPUT = ROOT / "schemas/m1/checkpoint_prototype.json"
FILE_IDENTIFIER = b"MSCP"
CHECKPOINT_SCHEMA_VERSION = 1
SUPPORTED_REQUIRED_FEATURES = frozenset({"canonical-payload-v1", "sha256"})


class CheckpointError(ValueError):
    """Raised when an M1 checkpoint envelope cannot be safely loaded."""


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _string_vector(
    builder: flatbuffers.Builder,
    values: tuple[bytes, ...],
) -> int:
    offsets = [builder.CreateString(value) for value in values]
    builder.StartVector(4, len(offsets), 4)
    for offset in reversed(offsets):
        builder.PrependUOffsetTRelative(offset)
    return builder.EndVector()


def build_checkpoint(
    payload: bytes,
    *,
    schema_version: int = CHECKPOINT_SCHEMA_VERSION,
    canonical_encoding_version: int = CANONICAL_ENCODING_VERSION,
    engine_version: str = "0.1.0-m1",
    payload_kind: str = "m1-prototype",
    required_features: tuple[str, ...] = ("canonical-payload-v1", "sha256"),
    extensions: dict[str, Any] | None = None,
    future_optional: str | None = None,
) -> bytes:
    """Build deterministic FlatBuffer bytes without generated runtime code."""

    builder = flatbuffers.Builder(1024)
    engine_offset = builder.CreateString(engine_version)
    kind_offset = builder.CreateString(payload_kind)
    payload_offset = builder.CreateByteVector(payload)
    digest_offset = builder.CreateByteVector(sha256(payload).digest())
    features_offset = _string_vector(
        builder,
        tuple(item.encode("utf-8") for item in sorted(required_features)),
    )
    extensions_offset = builder.CreateString(
        canonical_encode(extensions or {}).decode("utf-8")
    )
    future_offset = (
        builder.CreateString(future_optional)
        if future_optional is not None
        else None
    )
    builder.StartObject(9 if future_offset is not None else 8)
    builder.PrependUint32Slot(0, schema_version, 0)
    builder.PrependUint32Slot(
        1,
        canonical_encoding_version,
        0,
    )
    builder.PrependUOffsetTRelativeSlot(2, engine_offset, 0)
    builder.PrependUOffsetTRelativeSlot(3, kind_offset, 0)
    builder.PrependUOffsetTRelativeSlot(4, payload_offset, 0)
    builder.PrependUOffsetTRelativeSlot(5, digest_offset, 0)
    builder.PrependUOffsetTRelativeSlot(6, features_offset, 0)
    builder.PrependUOffsetTRelativeSlot(7, extensions_offset, 0)
    if future_offset is not None:
        builder.PrependUOffsetTRelativeSlot(8, future_offset, 0)
    root = builder.EndObject()
    builder.Finish(root, file_identifier=FILE_IDENTIFIER)
    return bytes(builder.Output())


def _offset(table: Table, slot: int, *, required: bool = True) -> int:
    result = table.Offset(4 + slot * 2)
    if result == 0 and required:
        raise CheckpointError(f"required envelope slot {slot} is absent")
    return result


def _uint32(table: Table, slot: int) -> int:
    offset = _offset(table, slot)
    return table.Get(number_types.Uint32Flags, table.Pos + offset)


def _string(table: Table, slot: int) -> str:
    offset = _offset(table, slot)
    raw = bytes(table.String(table.Pos + offset))
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CheckpointError(f"envelope slot {slot} is not UTF-8") from error


def _byte_vector(table: Table, slot: int) -> bytes:
    offset = _offset(table, slot)
    start = table.Vector(offset)
    size = table.VectorLen(offset)
    end = start + size
    if start < 0 or end > len(table.Bytes):
        raise CheckpointError(f"envelope slot {slot} exceeds the input")
    return bytes(table.Bytes[start:end])


def _string_vector_values(table: Table, slot: int) -> tuple[str, ...]:
    offset = _offset(table, slot)
    start = table.Vector(offset)
    size = table.VectorLen(offset)
    values: list[str] = []
    for index in range(size):
        try:
            values.append(bytes(table.String(start + index * 4)).decode("utf-8"))
        except UnicodeDecodeError as error:
            raise CheckpointError("required feature is not UTF-8") from error
    return tuple(values)


def load_checkpoint(data: bytes) -> dict[str, Any]:
    """Load an envelope, enforce compatibility, and verify its payload."""

    try:
        if len(data) < 12 or data[4:8] != FILE_IDENTIFIER:
            raise CheckpointError("checkpoint identifier is absent or invalid")
        root = encode.Get(packer.uoffset, data, 0)
        if root < 8 or root >= len(data):
            raise CheckpointError("checkpoint root offset is outside the input")
        table = Table(bytearray(data), root)
        schema_version = _uint32(table, 0)
        encoding_version = _uint32(table, 1)
        engine_version = _string(table, 2)
        payload_kind = _string(table, 3)
        payload = _byte_vector(table, 4)
        payload_digest = _byte_vector(table, 5)
        required_features = _string_vector_values(table, 6)
        extensions_bytes = _string(table, 7).encode("utf-8")
    except CheckpointError:
        raise
    except (
        IndexError,
        OverflowError,
        struct.error,
        UnicodeError,
        ValueError,
    ) as error:
        raise CheckpointError("checkpoint structure is truncated or invalid") from error
    if schema_version < 1:
        raise CheckpointError("checkpoint schema version is invalid")
    if encoding_version != CANONICAL_ENCODING_VERSION:
        raise CheckpointError("canonical encoding version is unsupported")
    if not engine_version or not payload_kind:
        raise CheckpointError("checkpoint identity fields are empty")
    unknown_features = sorted(
        set(required_features).difference(SUPPORTED_REQUIRED_FEATURES)
    )
    if unknown_features:
        raise CheckpointError(
            "checkpoint requires unsupported features: "
            + ", ".join(unknown_features)
        )
    if len(payload_digest) != 32 or sha256(payload).digest() != payload_digest:
        raise CheckpointError("checkpoint payload checksum does not match")
    try:
        decoded_payload = canonical_decode(payload)
        extensions = canonical_decode(extensions_bytes)
    except CanonicalEncodingError as error:
        raise CheckpointError("checkpoint contains noncanonical metadata") from error
    if not isinstance(extensions, dict):
        raise CheckpointError("checkpoint extensions must be an object")
    return {
        "schema_version": schema_version,
        "canonical_encoding_version": encoding_version,
        "engine_version": engine_version,
        "payload_kind": payload_kind,
        "payload": decoded_payload,
        "payload_sha256": payload_digest.hex(),
        "required_features": required_features,
        "extensions": extensions,
    }


def canonical_vectors() -> dict[str, Any]:
    valid_values = {
        "binary": {"blob": bytes.fromhex("00017fff")},
        "f64-endian": {
            "negative_zero": -0.0,
            "one": 1.0,
            "smallest_subnormal": 5e-324,
        },
        "integer-boundaries": {
            "maximum": (1 << 63) - 1,
            "minimum": -(1 << 63),
        },
        "unicode-nfc": {"angstrom": "A\u030a", "currency": "€", "name": "Zürich"},
    }
    valid = []
    for case_id, value in sorted(valid_values.items()):
        encoded = canonical_encode(value)
        canonical_decode(encoded)
        valid.append(
            {
                "id": case_id,
                "canonical_hex": encoded.hex(),
                "sha256": sha256(encoded).hexdigest(),
            }
        )
    invalid_bytes = {
        "duplicate-key": b'{"a":1,"a":2}\n',
        "invalid-byte-tag": b'{"$bytes":"0G"}\n',
        "invalid-utf8": b'{"x":"\xff"}\n',
        "missing-terminal-lf": b'{"x":1}',
        "noncanonical-f64-case": b'{"$f64":"3FF0000000000000"}\n',
        "noncanonical-integer": b'{"x":01}\n',
        "nonfinite-number": b'{"x":NaN}\n',
        "raw-float": b'{"x":1.0}\n',
        "unknown-reserved-tag": b'{"$future":"required"}\n',
        "whitespace": b'{ "x": 1 }\n',
    }
    invalid = []
    for case_id, encoded in sorted(invalid_bytes.items()):
        try:
            canonical_decode(encoded)
        except CanonicalEncodingError as error:
            invalid.append(
                {
                    "id": case_id,
                    "input_hex": encoded.hex(),
                    "expected_error": str(error),
                }
            )
        else:
            raise AssertionError(f"invalid vector was accepted: {case_id}")
    return {
        "schema_version": "m1-canonical-encoding-v1",
        "canonical_encoding_version": CANONICAL_ENCODING_VERSION,
        "valid": valid,
        "invalid": invalid,
    }


def checkpoint_evidence() -> dict[str, Any]:
    payload = canonical_encode(
        {
            "agents": [7, 11, 19],
            "balance": 1250.5,
            "country": "AUR",
            "negative_zero_probe": -0.0,
        }
    )
    base = build_checkpoint(
        payload,
        extensions={"m0_contract": "frozen", "note": "M1 boundary prototype"},
    )
    parsed = load_checkpoint(base)
    future = build_checkpoint(
        payload,
        schema_version=2,
        extensions={"optional_revision": 2},
        future_optional="ignored-by-v1-reader",
    )
    future_parsed = load_checkpoint(future)
    payload_index = base.find(payload)
    if payload_index < 0:
        raise AssertionError("payload bytes are absent from checkpoint")
    checksum_corruption = bytearray(base)
    checksum_corruption[payload_index] ^= 0x01
    rejected_cases = {
        "checksum-corruption": bytes(checksum_corruption),
        "identifier-corruption": base[:4] + b"FAIL" + base[8:],
        "noncanonical-payload": build_checkpoint(b'{"x":1.0}\n'),
        "truncated": base[: len(base) // 2],
        "unknown-canonical-version": build_checkpoint(
            payload,
            canonical_encoding_version=2,
        ),
        "unknown-required-feature": build_checkpoint(
            payload,
            required_features=("canonical-payload-v1", "future.required", "sha256"),
        ),
    }
    rejected = []
    for case_id, encoded in sorted(rejected_cases.items()):
        try:
            load_checkpoint(encoded)
        except CheckpointError as error:
            rejected.append({"id": case_id, "expected_error": str(error)})
        else:
            raise AssertionError(f"corrupt checkpoint was accepted: {case_id}")
    semantic = {
        "schema_version": parsed["schema_version"],
        "canonical_encoding_version": parsed["canonical_encoding_version"],
        "engine_version": parsed["engine_version"],
        "payload_kind": parsed["payload_kind"],
        "payload_sha256": parsed["payload_sha256"],
        "required_features": list(parsed["required_features"]),
    }
    return {
        "schema_version": "m1-checkpoint-prototype-v1",
        "flatbuffer_file_identifier": FILE_IDENTIFIER.decode("ascii"),
        "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
        "canonical_encoding_version": CANONICAL_ENCODING_VERSION,
        "payload_size_bytes": len(payload),
        "envelope_size_bytes": len(base),
        "envelope_hex": base.hex(),
        "envelope_sha256": sha256(base).hexdigest(),
        "semantic_sha256": sha256(canonical_encode(semantic)).hexdigest(),
        "forward_compatibility": {
            "future_schema_version": future_parsed["schema_version"],
            "unknown_optional_field_ignored": True,
            "required_features_control_compatibility": True,
        },
        "rejected": rejected,
        "benchmark_budget": {
            "iterations": 1000,
            "maximum_median_encode_us": 1000,
            "maximum_median_decode_us": 1000,
        },
    }


def _write_or_check(path: Path, content: bytes, *, write: bool) -> bool:
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        print(f"write   {path.relative_to(ROOT)}")
        return True
    if not path.exists() or path.read_bytes() != content:
        print(f"stale   {path.relative_to(ROOT)}", file=sys.stderr)
        return False
    print(f"ok      {path.relative_to(ROOT)}")
    return True


def benchmark(iterations: int) -> None:
    payload = canonical_encode({"agents": list(range(32)), "value": 123.5})
    encoded = build_checkpoint(payload)
    encode_samples = []
    decode_samples = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        build_checkpoint(payload)
        encode_samples.append(time.perf_counter_ns() - start)
        start = time.perf_counter_ns()
        load_checkpoint(encoded)
        decode_samples.append(time.perf_counter_ns() - start)
    encode_us = statistics.median(encode_samples) / 1000
    decode_us = statistics.median(decode_samples) / 1000
    print(
        f"checkpoint benchmark: iterations={iterations} "
        f"encode_median_us={encode_us:.3f} decode_median_us={decode_us:.3f}"
    )
    if encode_us > 1000 or decode_us > 1000:
        raise SystemExit("checkpoint prototype exceeded its M1 median-time budget")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--benchmark", action="store_true")
    parser.add_argument("--iterations", type=int, default=1000)
    args = parser.parse_args()
    if args.benchmark:
        benchmark(args.iterations)
        return 0
    results = (
        _write_or_check(
            VECTOR_OUTPUT,
            _json_bytes(canonical_vectors()),
            write=args.write,
        ),
        _write_or_check(
            PROTOTYPE_OUTPUT,
            _json_bytes(checkpoint_evidence()),
            write=args.write,
        ),
    )
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
