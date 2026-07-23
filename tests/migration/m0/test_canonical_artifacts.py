from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.cpp_migration.common import (
    BaselineWriteError,
    M0Error,
    SchemaError,
    aggregate_hash,
    canonical_json_bytes,
    check_or_write_generated,
    require_unique_ids,
    sha256_bytes,
    validate_stable_id,
    write_new_canonical_json,
)


def test_canonical_json_is_sorted_ascii_compact_and_terminated():
    value = {"z": "policy", "a": "\u03b1", "nested": {"b": 2, "a": 1}}
    assert canonical_json_bytes(value) == (
        b'{"a":"\\u03b1","nested":{"a":1,"b":2},"z":"policy"}\n'
    )


def test_all_checked_json_schemas_are_valid_json_with_unique_ids():
    root = Path(__file__).resolve().parents[3]
    schemas = sorted((root / "schemas/m0/definitions").glob("*.schema.json"))
    assert schemas
    ids = []
    for path in schemas:
        value = json.loads(path.read_text(encoding="utf-8"))
        assert value["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        ids.append(value["$id"])
    assert len(ids) == len(set(ids))


def test_canonical_json_rejects_non_finite_and_non_json_values():
    with pytest.raises(SchemaError, match="canonical JSON"):
        canonical_json_bytes({"value": float("nan")})
    with pytest.raises(SchemaError, match="canonical JSON"):
        canonical_json_bytes({"value": object()})


def test_hashing_does_not_depend_on_mapping_insertion_order():
    left = {"b.json": "2", "a.json": "1"}
    right = {"a.json": "1", "b.json": "2"}
    assert aggregate_hash(left) == aggregate_hash(right)
    assert sha256_bytes(canonical_json_bytes(left)) == sha256_bytes(
        canonical_json_bytes(right)
    )


@pytest.mark.parametrize(
    "value",
    ["config.n_households", "policy:tax-income", "world.fx/rate", "m4.v0"],
)
def test_stable_id_accepts_qualified_lowercase_ids(value):
    assert validate_stable_id(value) == value


@pytest.mark.parametrize("value", ["", "Config.Field", "bad id", "_private", "a..b"])
def test_stable_id_rejects_unstable_or_ambiguous_ids(value):
    with pytest.raises(SchemaError):
        validate_stable_id(value)


def test_unique_ids_reject_duplicates():
    with pytest.raises(SchemaError, match="duplicate"):
        require_unique_ids([{"id": "policy.a"}, {"id": "policy.a"}])


def test_transient_writer_refuses_overwrite(tmp_path: Path):
    path = tmp_path / "artifact.json"
    write_new_canonical_json(path, {"schema_version": "test-v1"})
    with pytest.raises(BaselineWriteError, match="overwrite"):
        write_new_canonical_json(path, {"schema_version": "test-v2"})


def test_generated_writer_check_mode_never_repairs_stale_file(tmp_path: Path):
    path = tmp_path / "generated.json"
    value = {"schema_version": "test-v1", "value": 1}
    assert check_or_write_generated(path, value, check=False) is False
    assert check_or_write_generated(path, value, check=True) is True
    path.write_text(json.dumps({"schema_version": "test-v1", "value": 2}))
    before = path.read_bytes()
    with pytest.raises(M0Error, match="stale"):
        check_or_write_generated(path, value, check=True)
    assert path.read_bytes() == before
