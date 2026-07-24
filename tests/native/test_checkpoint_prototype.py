from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import struct
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools/m1"
sys.path.insert(0, str(TOOLS))

from canonical_encoding import (  # noqa: E402
    CanonicalEncodingError,
    canonical_decode,
    canonical_encode,
)
from checkpoint_prototype import (  # noqa: E402
    CheckpointError,
    build_checkpoint,
    canonical_vectors,
    checkpoint_evidence,
    load_checkpoint,
)
from dependency_report import build_spdx, load_and_validate  # noqa: E402


def test_checked_canonical_vectors_are_exact_and_executable() -> None:
    checked = json.loads(
        (ROOT / "schemas/m1/canonical_encoding_vectors.json").read_text(
            encoding="utf-8"
        )
    )
    assert checked == canonical_vectors()
    for case in checked["valid"]:
        data = bytes.fromhex(case["canonical_hex"])
        canonical_decode(data)
        assert sha256(data).hexdigest() == case["sha256"]
    for case in checked["invalid"]:
        with pytest.raises(CanonicalEncodingError, match=".+"):
            canonical_decode(bytes.fromhex(case["input_hex"]))


def test_canonical_encoding_preserves_f64_bits_and_normalizes_unicode() -> None:
    encoded = canonical_encode(
        {
            "decomposed": "A\u030a",
            "negative_zero": -0.0,
            "subnormal": 5e-324,
        }
    )
    decoded = canonical_decode(encoded)
    assert decoded["decomposed"] == "\u00c5"
    assert struct.pack(">d", decoded["negative_zero"]) == bytes.fromhex(
        "8000000000000000"
    )
    assert struct.pack(">d", decoded["subnormal"]) == bytes.fromhex(
        "0000000000000001"
    )


@pytest.mark.parametrize(
    "value",
    [
        math.inf,
        math.nan,
        1 << 63,
        {"$reserved": 1},
        {1: "non-string key"},
    ],
)
def test_canonical_encoder_rejects_ambiguous_values(value) -> None:
    with pytest.raises(CanonicalEncodingError):
        canonical_encode(value)


def test_checked_checkpoint_bytes_and_semantics_are_reproducible() -> None:
    checked = json.loads(
        (ROOT / "schemas/m1/checkpoint_prototype.json").read_text(encoding="utf-8")
    )
    assert checked == checkpoint_evidence()
    envelope = bytes.fromhex(checked["envelope_hex"])
    assert sha256(envelope).hexdigest() == checked["envelope_sha256"]
    loaded = load_checkpoint(envelope)
    assert loaded["schema_version"] == 1
    assert loaded["engine_version"] == "0.1.0-m1"
    assert loaded["payload"]["country"] == "AUR"


def test_checkpoint_compatibility_is_required_feature_driven() -> None:
    payload = canonical_encode({"state": "future"})
    future = build_checkpoint(
        payload,
        schema_version=7,
        future_optional="reader-must-ignore-this-optional-slot",
    )
    assert load_checkpoint(future)["schema_version"] == 7
    incompatible = build_checkpoint(
        payload,
        required_features=("canonical-payload-v1", "future.required", "sha256"),
    )
    with pytest.raises(CheckpointError, match="unsupported features"):
        load_checkpoint(incompatible)


def test_checkpoint_rejects_empty_identity_and_noncanonical_payload() -> None:
    with pytest.raises(CheckpointError, match="identity fields"):
        load_checkpoint(
            build_checkpoint(canonical_encode({}), engine_version="")
        )
    with pytest.raises(CheckpointError, match="noncanonical metadata"):
        load_checkpoint(build_checkpoint(b'{"raw_float":1.0}\n'))


def test_native_dependency_lock_has_complete_deterministic_spdx() -> None:
    lock = load_and_validate()
    checked = json.loads(
        (ROOT / "schemas/m1/native_sbom.spdx.json").read_text(encoding="utf-8")
    )
    assert checked == build_spdx(lock)
    assert len(checked["packages"]) == 5
    for package in checked["packages"]:
        assert package["licenseDeclared"] != "NOASSERTION"
        assert len(package["checksums"][0]["checksumValue"]) == 64
