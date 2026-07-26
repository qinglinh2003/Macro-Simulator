"""Process-local content-addressed storage for controller audit chunks.

The live controller keeps only bounded working tails in memory.  Immutable
historical chunks are written to a process-private temporary directory and are
identified solely by their SHA-256 digest in canonical controller state.
Portable checkpoints carry a binary package containing every referenced chunk;
restoration imports and verifies that package before decoding the controller
envelope.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile


ARCHIVE_MAGIC = b"MSCTARCH"
ARCHIVE_VERSION = 1
_ARCHIVE_HEADER = struct.Struct("<8sII")
_ARCHIVE_ENTRY = struct.Struct("<32sQ")
_STORE_ROOT = (
    Path(tempfile.gettempdir())
    / f"macro-sim-controller-chunks-{os.getpid()}"
)
CHAIN_NODE_FORMAT = "macro-sim-controller-chunk-chain-v1"


def _chunk_path(digest: str) -> Path:
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("controller chunk digest is malformed")
    return _STORE_ROOT / f"{digest}.bin"


def put_chunk(payload: bytes) -> str:
    """Store immutable bytes and return their verified content digest."""
    if not isinstance(payload, bytes) or not payload:
        raise TypeError("controller chunk payload must be non-empty bytes")
    digest = hashlib.sha256(payload).hexdigest()
    path = _chunk_path(digest)
    _STORE_ROOT.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        if path.read_bytes() != payload:
            raise RuntimeError("controller chunk digest collision")
        return digest
    temporary = _STORE_ROOT / f".{digest}.{os.getpid()}.tmp"
    temporary.write_bytes(payload)
    os.replace(temporary, path)
    return digest


def get_chunk(digest: str) -> bytes:
    """Load a chunk and reject missing or content-corrupt data."""
    path = _chunk_path(digest)
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ValueError(
            f"controller chunk {digest} is unavailable"
        ) from exc
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError(f"controller chunk {digest} is corrupt")
    return payload


def export_chunk_package(digests: Iterable[str]) -> bytes:
    """Build a deterministic portable package for the selected chunks."""
    ordered = sorted(set(digests))
    payload = bytearray(_ARCHIVE_HEADER.pack(
        ARCHIVE_MAGIC, ARCHIVE_VERSION, len(ordered),
    ))
    for digest in ordered:
        chunk = get_chunk(digest)
        payload.extend(_ARCHIVE_ENTRY.pack(bytes.fromhex(digest), len(chunk)))
        payload.extend(chunk)
    return bytes(payload)


def import_chunk_package(payload: bytes) -> tuple[str, ...]:
    """Verify and install every chunk from a portable package."""
    if not isinstance(payload, bytes):
        raise TypeError("controller archive package must be bytes")
    if len(payload) < _ARCHIVE_HEADER.size:
        raise ValueError("controller archive package is truncated")
    magic, version, count = _ARCHIVE_HEADER.unpack_from(payload)
    if magic != ARCHIVE_MAGIC or version != ARCHIVE_VERSION:
        raise ValueError("controller archive package header is invalid")
    position = _ARCHIVE_HEADER.size
    digests: list[str] = []
    previous = ""
    for _ in range(count):
        if position + _ARCHIVE_ENTRY.size > len(payload):
            raise ValueError("controller archive entry is truncated")
        raw_digest, size = _ARCHIVE_ENTRY.unpack_from(payload, position)
        position += _ARCHIVE_ENTRY.size
        if size == 0 or size > len(payload) - position:
            raise ValueError("controller archive entry size is invalid")
        chunk = bytes(payload[position:position + size])
        position += size
        digest = raw_digest.hex()
        if digest <= previous:
            raise ValueError(
                "controller archive entries are not strictly digest ordered"
            )
        if hashlib.sha256(chunk).hexdigest() != digest:
            raise ValueError("controller archive entry digest does not match")
        if put_chunk(chunk) != digest:
            raise RuntimeError("controller archive import changed a digest")
        digests.append(digest)
        previous = digest
    if position != len(payload):
        raise ValueError("controller archive package has trailing bytes")
    return tuple(digests)


class ChunkChainIndex:
    """A constant-resident append-only chain of JSON descriptors."""

    def __init__(
        self, *, head_sha256: str | None = None, count: int = 0,
    ) -> None:
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise TypeError("chunk-chain count must be a non-negative integer")
        if (count == 0) != (head_sha256 is None):
            raise ValueError("chunk-chain head and count disagree")
        if head_sha256 is not None:
            _chunk_path(head_sha256)
        self._head_sha256 = head_sha256
        self._count = count
        self._walk(newest_first=True)

    @staticmethod
    def _encode_node(
        descriptor: Mapping[str, object], previous_sha256: str | None,
    ) -> bytes:
        return (
            json.dumps(
                {
                    "descriptor": dict(descriptor),
                    "format": CHAIN_NODE_FORMAT,
                    "previous_sha256": previous_sha256,
                },
                ensure_ascii=True, allow_nan=False,
                separators=(",", ":"), sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

    @classmethod
    def _decode_node(cls, digest: str) -> dict[str, object]:
        payload = get_chunk(digest)
        try:
            document = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("chunk-chain node is not valid JSON") from exc
        if (
            not isinstance(document, dict)
            or set(document) != {
                "descriptor", "format", "previous_sha256",
            }
            or document["format"] != CHAIN_NODE_FORMAT
            or not isinstance(document["descriptor"], dict)
            or (
                document["previous_sha256"] is not None
                and not isinstance(document["previous_sha256"], str)
            )
            or cls._encode_node(
                document["descriptor"], document["previous_sha256"],
            ) != payload
        ):
            raise ValueError("chunk-chain node is invalid")
        if document["previous_sha256"] is not None:
            _chunk_path(document["previous_sha256"])
        return document

    def _walk(
        self, *, newest_first: bool,
    ) -> list[tuple[str, dict[str, object]]]:
        output: list[tuple[str, dict[str, object]]] = []
        digest = self._head_sha256
        seen: set[str] = set()
        while digest is not None:
            if digest in seen:
                raise ValueError("chunk-chain contains a cycle")
            seen.add(digest)
            document = self._decode_node(digest)
            output.append((digest, document))
            digest = document["previous_sha256"]
            if len(output) > self._count:
                raise ValueError("chunk-chain exceeds its declared count")
        if len(output) != self._count:
            raise ValueError("chunk-chain count does not match")
        if not newest_first:
            output.reverse()
        return output

    def append(self, descriptor: Mapping[str, object]) -> None:
        if not isinstance(descriptor, Mapping):
            raise TypeError("chunk-chain descriptor must be a mapping")
        payload = self._encode_node(descriptor, self._head_sha256)
        self._head_sha256 = put_chunk(payload)
        self._count += 1

    def clear(self) -> None:
        self._head_sha256 = None
        self._count = 0

    def __len__(self) -> int:
        return self._count

    def __iter__(self) -> Iterator[dict[str, object]]:
        for _digest, document in self._walk(newest_first=False):
            yield dict(document["descriptor"])

    def __reversed__(self) -> Iterator[dict[str, object]]:
        for _digest, document in self._walk(newest_first=True):
            yield dict(document["descriptor"])

    @property
    def node_digests(self) -> tuple[str, ...]:
        return tuple(
            digest for digest, _document
            in self._walk(newest_first=False)
        )

    def to_state(self) -> dict[str, object]:
        return {
            "count": self._count,
            "head_sha256": self._head_sha256,
        }

    @classmethod
    def from_state(cls, state: Mapping[str, object]) -> "ChunkChainIndex":
        if not isinstance(state, Mapping) or set(state) != {
            "count", "head_sha256",
        }:
            raise ValueError("chunk-chain state fields are invalid")
        return cls(
            count=state["count"],
            head_sha256=state["head_sha256"],
        )
