#!/usr/bin/env python3
"""Generate checked Philox and portable-sampling golden vectors."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from rng_reference import Philox, float_bits, philox4x32_10


ROOT = Path(__file__).resolve().parents[2]
JSON_OUTPUT = ROOT / "schemas/m1/rng_vectors.json"
CPP_OUTPUT = ROOT / "native/include/macro_sim/generated/rng_vectors.hpp"


def canonical_bytes(value) -> bytes:
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


def build_vectors() -> dict:
    block_inputs = [
        ((0, 0, 0, 0), (0, 0)),
        ((1, 0, 0, 0), (0, 0)),
        ((0, 1, 2, 3), (4, 5)),
        ((0xFFFFFFFF,) * 4, (0xFFFFFFFF, 0xFFFFFFFF)),
    ]
    blocks = [
        {
            "counter": list(counter),
            "key": list(key),
            "output": list(philox4x32_10(counter, key)),
        }
        for counter, key in block_inputs
    ]

    stream = Philox((0x12345678, 0x9ABCDEF0), (7, 6, 5, 4))
    u32 = [stream.u32() for _ in range(16)]

    uniform_rng = Philox((11, 29))
    uniform_bits = [float_bits(uniform_rng.uniform()) for _ in range(8)]
    open_bits = [float_bits(uniform_rng.uniform_open()) for _ in range(8)]

    bounded_rng = Philox((31, 37))
    bounded = [
        {"bound": bound, "value": bounded_rng.bounded(bound)}
        for bound in (1, 2, 3, 7, 10, 257, (1 << 32) - 5)
    ]

    bernoulli_rng = Philox((41, 43))
    bernoulli = [
        {"probability": probability, "value": bernoulli_rng.bernoulli(probability)}
        for probability in (0.0, 0.1, 0.5, 0.9, 1.0)
    ]

    shuffle_rng = Philox((47, 53))
    shuffled = list(range(12))
    shuffle_rng.shuffle(shuffled)
    sampled = shuffle_rng.sample(20, 7)

    normal_rng = Philox((59, 61))
    normal_bits = [float_bits(normal_rng.normal()) for _ in range(6)]

    poisson_rng = Philox((67, 71))
    poisson = [
        {"lambda": rate, "value": poisson_rng.poisson(rate)}
        for rate in (0.0, 0.25, 1.0, 4.0, 17.0, 40.0)
    ]

    payload = {
        "schema_version": "m1-rng-vectors-v1",
        "algorithm": "philox4x32-10",
        "counter_endianness": "little-word-first",
        "u64_word_order": "low32-then-high32",
        "normal_algorithm": "irwin-hall-12",
        "poisson_algorithm": "chunked-knuth-16",
        "blocks": blocks,
        "stream": {
            "counter": [7, 6, 5, 4],
            "key": [0x12345678, 0x9ABCDEF0],
            "u32": u32,
        },
        "uniform_bits": uniform_bits,
        "open_uniform_bits": open_bits,
        "bounded": bounded,
        "bernoulli": bernoulli,
        "shuffle": shuffled,
        "sample": sampled,
        "normal_bits": normal_bits,
        "poisson": poisson,
    }
    semantic = canonical_bytes(payload)
    return {
        **payload,
        "semantic_sha256": sha256(semantic).hexdigest(),
    }


def cpp_float(value: float) -> str:
    return format(value, ".17g")


def render_cpp(data: dict) -> bytes:
    lines = [
        "#ifndef MACRO_SIM_GENERATED_RNG_VECTORS_HPP",
        "#define MACRO_SIM_GENERATED_RNG_VECTORS_HPP",
        "",
        "#include <array>",
        "#include <cstdint>",
        "#include <string_view>",
        "",
        "namespace macro_sim::generated {",
        "",
        f"inline constexpr std::string_view kRngSemanticSha256 = \"{data['semantic_sha256']}\";",
        "",
        "struct PhiloxBlockVector final {",
        "    std::array<std::uint32_t, 4> counter;",
        "    std::array<std::uint32_t, 2> key;",
        "    std::array<std::uint32_t, 4> output;",
        "};",
        f"inline constexpr std::array<PhiloxBlockVector, {len(data['blocks'])}> kPhiloxBlockVectors{{{{",
    ]
    for item in data["blocks"]:
        counter = ", ".join(f"{value}U" for value in item["counter"])
        key = ", ".join(f"{value}U" for value in item["key"])
        output = ", ".join(f"{value}U" for value in item["output"])
        lines.append(f"    {{{{{counter}}}, {{{key}}}, {{{output}}}}},")
    lines.extend(
        [
            "}};",
            "",
            f"inline constexpr std::array<std::uint32_t, {len(data['stream']['u32'])}> kStreamU32{{{{",
            "    " + ", ".join(f"{value}U" for value in data["stream"]["u32"]),
            "}};",
            f"inline constexpr std::array<std::uint64_t, {len(data['uniform_bits'])}> kUniformBits{{{{",
            "    " + ", ".join(f"{value}ULL" for value in data["uniform_bits"]),
            "}};",
            f"inline constexpr std::array<std::uint64_t, {len(data['open_uniform_bits'])}> kOpenUniformBits{{{{",
            "    " + ", ".join(f"{value}ULL" for value in data["open_uniform_bits"]),
            "}};",
            "",
            "struct BoundedVector final { std::uint64_t bound; std::uint64_t value; };",
            f"inline constexpr std::array<BoundedVector, {len(data['bounded'])}> kBoundedVectors{{{{",
        ]
    )
    for item in data["bounded"]:
        lines.append(f"    {{{item['bound']}ULL, {item['value']}ULL}},")
    lines.extend(
        [
            "}};",
            "",
            "struct BernoulliVector final { double probability; bool value; };",
            f"inline constexpr std::array<BernoulliVector, {len(data['bernoulli'])}> kBernoulliVectors{{{{",
        ]
    )
    for item in data["bernoulli"]:
        lines.append(
            f"    {{{cpp_float(item['probability'])}, {str(item['value']).lower()}}},"
        )
    lines.extend(
        [
            "}};",
            f"inline constexpr std::array<std::size_t, {len(data['shuffle'])}> kShuffleVector{{{{",
            "    " + ", ".join(str(value) for value in data["shuffle"]),
            "}};",
            f"inline constexpr std::array<std::size_t, {len(data['sample'])}> kSampleVector{{{{",
            "    " + ", ".join(str(value) for value in data["sample"]),
            "}};",
            f"inline constexpr std::array<std::uint64_t, {len(data['normal_bits'])}> kNormalBits{{{{",
            "    " + ", ".join(f"{value}ULL" for value in data["normal_bits"]),
            "}};",
            "",
            "struct PoissonVector final { double lambda; std::uint64_t value; };",
            f"inline constexpr std::array<PoissonVector, {len(data['poisson'])}> kPoissonVectors{{{{",
        ]
    )
    for item in data["poisson"]:
        lines.append(f"    {{{cpp_float(item['lambda'])}, {item['value']}ULL}},")
    lines.extend(
        [
            "}};",
            "",
            "}  // namespace macro_sim::generated",
            "",
            "#endif",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def write_or_check(path: Path, content: bytes, *, check: bool) -> None:
    if path.exists() and path.read_bytes() == content:
        print(f"ok      {path.relative_to(ROOT)}")
        return
    if check:
        state = "missing" if not path.exists() else "stale"
        raise RuntimeError(f"{state} generated artifact: {path.relative_to(ROOT)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    print(f"written {path.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        data = build_vectors()
        write_or_check(JSON_OUTPUT, canonical_bytes(data), check=args.check)
        write_or_check(CPP_OUTPUT, render_cpp(data), check=args.check)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"M1 RNG vector error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
