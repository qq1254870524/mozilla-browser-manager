"""Profile-stable deterministic PRNG — fixed noise pattern per profile."""
from __future__ import annotations

import hashlib
import struct
from typing import Iterator


def profile_seed(profile_id: str, *, salt: str = "mozilla-v6-stealth") -> bytes:
    raw = f"{salt}:{profile_id}".encode("utf-8")
    return hashlib.sha256(raw).digest()


def seed_hex(profile_id: str, *, salt: str = "mozilla-v6-stealth") -> str:
    return profile_seed(profile_id, salt=salt).hex()


class StableRNG:
    """SHA256 counter RNG — same profile_id => identical stream forever."""

    def __init__(self, profile_id: str, *, salt: str = "mozilla-v6-stealth", stream: str = "main") -> None:
        self._base = hashlib.sha256(profile_seed(profile_id, salt=salt) + stream.encode()).digest()
        self._counter = 0

    def _block(self) -> bytes:
        self._counter += 1
        return hashlib.sha256(self._base + self._counter.to_bytes(8, "big")).digest()

    def randbytes(self, n: int) -> bytes:
        out = bytearray()
        while len(out) < n:
            out.extend(self._block())
        return bytes(out[:n])

    def randint(self, a: int, b: int) -> int:
        if b < a:
            a, b = b, a
        span = b - a + 1
        # rejection sampling
        while True:
            raw = int.from_bytes(self.randbytes(8), "big")
            if raw < (2**64 // span) * span:
                return a + (raw % span)

    def choice(self, seq):
        return seq[self.randint(0, len(seq) - 1)]

    def sample(self, seq, k: int):
        items = list(seq)
        out = []
        for _ in range(min(k, len(items))):
            i = self.randint(0, len(items) - 1)
            out.append(items.pop(i))
        return out

    def random(self) -> float:
        return int.from_bytes(self.randbytes(8), "big") / float(2**64)

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        # Box-Muller
        u1 = max(self.random(), 1e-12)
        u2 = self.random()
        import math

        z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        return mu + z * sigma

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self.random()

    def derive_int(self, name: str, a: int, b: int) -> int:
        h = hashlib.sha256(self._base + name.encode()).digest()
        span = b - a + 1
        return a + (int.from_bytes(h[:8], "big") % span)

    def derive_float(self, name: str, a: float, b: float) -> float:
        h = hashlib.sha256(self._base + name.encode()).digest()
        x = int.from_bytes(h[:8], "big") / float(2**64)
        return a + (b - a) * x
