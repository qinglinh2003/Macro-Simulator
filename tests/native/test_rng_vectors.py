from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/m1"))

from rng_reference import Philox, float_bits, philox4x32_10  # noqa: E402


def test_checked_philox_and_sampling_vectors_match_python_reference() -> None:
    data = json.loads(
        (ROOT / "schemas/m1/rng_vectors.json").read_text(encoding="utf-8")
    )
    for item in data["blocks"]:
        assert list(philox4x32_10(tuple(item["counter"]), tuple(item["key"]))) == item[
            "output"
        ]

    stream = Philox(tuple(data["stream"]["key"]), tuple(data["stream"]["counter"]))
    assert [stream.u32() for _ in data["stream"]["u32"]] == data["stream"]["u32"]

    uniform = Philox((11, 29))
    assert [float_bits(uniform.uniform()) for _ in data["uniform_bits"]] == data[
        "uniform_bits"
    ]
    assert [
        float_bits(uniform.uniform_open()) for _ in data["open_uniform_bits"]
    ] == data["open_uniform_bits"]

    bounded = Philox((31, 37))
    assert [bounded.bounded(item["bound"]) for item in data["bounded"]] == [
        item["value"] for item in data["bounded"]
    ]

    bernoulli = Philox((41, 43))
    assert [
        bernoulli.bernoulli(item["probability"]) for item in data["bernoulli"]
    ] == [item["value"] for item in data["bernoulli"]]

    permutations = Philox((47, 53))
    shuffled = list(range(12))
    permutations.shuffle(shuffled)
    assert shuffled == data["shuffle"]
    assert permutations.sample(20, 7) == data["sample"]

    normal = Philox((59, 61))
    assert [float_bits(normal.normal()) for _ in data["normal_bits"]] == data[
        "normal_bits"
    ]

    poisson = Philox((67, 71))
    assert [poisson.poisson(item["lambda"]) for item in data["poisson"]] == [
        item["value"] for item in data["poisson"]
    ]
