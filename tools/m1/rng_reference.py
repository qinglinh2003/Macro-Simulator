"""Pure-Python reference for the M1 Philox and sampling contract."""

from __future__ import annotations

import math
import struct


MASK32 = (1 << 32) - 1
MASK64 = (1 << 64) - 1
M0 = 0xD2511F53
M1 = 0xCD9E8D57
W0 = 0x9E3779B9
W1 = 0xBB67AE85
TWO_NEGATIVE_53 = 1.0 / (1 << 53)


def _multiply_high_low(left: int, right: int) -> tuple[int, int]:
    product = left * right
    return (product >> 32) & MASK32, product & MASK32


def philox4x32_10(
    counter: tuple[int, int, int, int],
    key: tuple[int, int],
) -> tuple[int, int, int, int]:
    words = tuple(item & MASK32 for item in counter)
    key0, key1 = (item & MASK32 for item in key)
    for _ in range(10):
        high0, low0 = _multiply_high_low(M0, words[0])
        high1, low1 = _multiply_high_low(M1, words[2])
        words = (
            high1 ^ words[1] ^ key0,
            low1,
            high0 ^ words[3] ^ key1,
            low0,
        )
        key0 = (key0 + W0) & MASK32
        key1 = (key1 + W1) & MASK32
    return words


class Philox:
    def __init__(
        self,
        key: tuple[int, int],
        counter: tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> None:
        self.key = tuple(item & MASK32 for item in key)
        self.counter = list(item & MASK32 for item in counter)
        self.block: tuple[int, ...] = ()
        self.block_index = 4

    def _increment(self) -> None:
        for index in range(4):
            self.counter[index] = (self.counter[index] + 1) & MASK32
            if self.counter[index] != 0:
                return

    def u32(self) -> int:
        if self.block_index >= 4:
            self.block = philox4x32_10(tuple(self.counter), self.key)
            self._increment()
            self.block_index = 0
        value = self.block[self.block_index]
        self.block_index += 1
        return value

    def u64(self) -> int:
        return self.u32() | (self.u32() << 32)

    def uniform(self) -> float:
        return (self.u64() >> 11) * TWO_NEGATIVE_53

    def uniform_open(self) -> float:
        return ((self.u64() >> 11) + 0.5) * TWO_NEGATIVE_53

    def bernoulli(self, probability: float) -> bool:
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ValueError("invalid Bernoulli probability")
        if probability == 0.0:
            return False
        if probability == 1.0:
            return True
        return self.uniform() < probability

    def bounded(self, bound: int) -> int:
        if bound <= 0 or bound > MASK64:
            raise ValueError("invalid bound")
        threshold = ((-bound) & MASK64) % bound
        while True:
            value = self.u64()
            if value >= threshold:
                return value % bound

    def shuffle(self, values: list[int]) -> None:
        for remaining in range(len(values), 1, -1):
            selected = self.bounded(remaining)
            values[remaining - 1], values[selected] = (
                values[selected],
                values[remaining - 1],
            )

    def sample(self, population_size: int, sample_size: int) -> list[int]:
        if sample_size > population_size:
            raise ValueError("sample exceeds population")
        values = list(range(population_size))
        for offset in range(sample_size):
            selected = offset + self.bounded(population_size - offset)
            values[offset], values[selected] = values[selected], values[offset]
        return values[:sample_size]

    def normal(self) -> float:
        total = 0.0
        for _ in range(12):
            total += self.uniform()
        return total - 6.0

    def poisson(self, rate: float) -> int:
        if not math.isfinite(rate) or rate < 0:
            raise ValueError("invalid Poisson rate")
        total = 0
        remaining = rate
        while remaining > 0:
            chunk = min(remaining, 16.0)
            limit = math.exp(-chunk)
            count = 0
            product = 1.0
            while True:
                count += 1
                product *= self.uniform_open()
                if product <= limit:
                    break
            total += count - 1
            remaining -= chunk
        return total


def float_bits(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]
