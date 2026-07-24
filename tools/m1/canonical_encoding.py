#!/usr/bin/env python3
"""Canonical metadata encoding used at native persistence boundaries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
import struct
import unicodedata
from typing import Any


CANONICAL_ENCODING_VERSION = 1
_INT64_MIN = -(1 << 63)
_INT64_MAX = (1 << 63) - 1
_RESERVED_PREFIX = "$"


class CanonicalEncodingError(ValueError):
    """Raised when a value or byte sequence is not canonical."""


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _wire_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if not _INT64_MIN <= value <= _INT64_MAX:
            raise CanonicalEncodingError("integer is outside signed 64-bit range")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalEncodingError("nonfinite floating-point value")
        bits = struct.unpack(">Q", struct.pack(">d", value))[0]
        return {"$f64": f"{bits:016x}"}
    if isinstance(value, bytes):
        return {"$bytes": value.hex()}
    if isinstance(value, str):
        return _normalized(value)
    if isinstance(value, Mapping):
        encoded: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise CanonicalEncodingError("object key is not a string")
            key = _normalized(raw_key)
            if key.startswith(_RESERVED_PREFIX):
                raise CanonicalEncodingError("object key uses a reserved prefix")
            if key in encoded:
                raise CanonicalEncodingError(
                    "object keys collide after Unicode normalization"
                )
            encoded[key] = _wire_value(item)
        return encoded
    if isinstance(value, Sequence):
        return [_wire_value(item) for item in value]
    raise CanonicalEncodingError(f"unsupported value type: {type(value).__name__}")


def canonical_encode(value: Any) -> bytes:
    """Encode a supported value as canonical UTF-8 JSON plus one LF."""

    wire = _wire_value(value)
    return (
        json.dumps(
            wire,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CanonicalEncodingError(f"duplicate object key: {key}")
        value[key] = item
    return value


def _reject_float(_: str) -> Any:
    raise CanonicalEncodingError("raw JSON floating-point number is forbidden")


def _reject_constant(value: str) -> Any:
    raise CanonicalEncodingError(f"nonfinite JSON number is forbidden: {value}")


def _native_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if not _INT64_MIN <= value <= _INT64_MAX:
            raise CanonicalEncodingError("integer is outside signed 64-bit range")
        return value
    if isinstance(value, str):
        if value != _normalized(value):
            raise CanonicalEncodingError("string is not Unicode NFC")
        return value
    if isinstance(value, list):
        return [_native_value(item) for item in value]
    if not isinstance(value, dict):
        raise CanonicalEncodingError("unsupported JSON value")
    if set(value) == {"$f64"}:
        encoded = value["$f64"]
        if (
            not isinstance(encoded, str)
            or len(encoded) != 16
            or any(character not in "0123456789abcdef" for character in encoded)
        ):
            raise CanonicalEncodingError("invalid canonical f64 bit pattern")
        result = struct.unpack(">d", struct.pack(">Q", int(encoded, 16)))[0]
        if not math.isfinite(result):
            raise CanonicalEncodingError("nonfinite canonical f64 bit pattern")
        return result
    if set(value) == {"$bytes"}:
        encoded = value["$bytes"]
        if (
            not isinstance(encoded, str)
            or len(encoded) % 2 != 0
            or any(character not in "0123456789abcdef" for character in encoded)
        ):
            raise CanonicalEncodingError("invalid canonical byte string")
        return bytes.fromhex(encoded)
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key != _normalized(key):
            raise CanonicalEncodingError("object key is not Unicode NFC")
        if key.startswith(_RESERVED_PREFIX):
            raise CanonicalEncodingError("unknown reserved canonical tag")
        result[key] = _native_value(item)
    return result


def canonical_decode(data: bytes) -> Any:
    """Decode canonical bytes and reject alternative representations."""

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CanonicalEncodingError("input is not valid UTF-8") from error
    try:
        wire = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except CanonicalEncodingError:
        raise
    except (json.JSONDecodeError, ValueError) as error:
        raise CanonicalEncodingError("input is not valid canonical JSON") from error
    native = _native_value(wire)
    if canonical_encode(native) != data:
        raise CanonicalEncodingError("input has a noncanonical representation")
    return native
