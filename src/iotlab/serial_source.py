"""Hardware-independent serial reading.

``SerialReader`` works on anything with a ``readline() -> bytes`` method, so the
same code runs against a real ``serial.Serial`` port or ``SimulatedSerial``.
"""

from __future__ import annotations

import math
import random
from typing import Iterator, Optional, Protocol

from .parser import ParseError, Reading, format_line, parse_line


class LineSource(Protocol):
    def readline(self) -> bytes: ...


class SerialReader:
    """Yields valid :class:`Reading` objects, counting corrupted lines."""

    def __init__(self, source: LineSource) -> None:
        self.source = source
        self.good = 0
        self.bad = 0

    @classmethod
    def open(cls, port: str, baudrate: int = 9600, timeout: float = 2.0) -> "SerialReader":
        import serial  # imported lazily so tests need no hardware

        return cls(serial.Serial(port, baudrate, timeout=timeout))

    def __iter__(self) -> Iterator[Reading]:
        while True:
            raw = self.source.readline()
            if not raw:  # timeout or end of stream
                return
            try:
                reading = parse_line(raw.decode("ascii", errors="replace"))
            except ParseError:
                self.bad += 1
                continue
            self.good += 1
            yield reading

    def read_one(self) -> Optional[Reading]:
        return next(iter(self), None)


class SimulatedSerial:
    """Fake port producing DHT-style frames: a slow sine wave plus noise.

    Args:
        count: number of lines before the stream ends (``None`` = endless).
        corrupt_every: every n-th line gets a flipped character (0 = never).
    """

    def __init__(self, count: Optional[int] = 10, interval_ms: int = 2000,
                 corrupt_every: int = 0, seed: int = 0) -> None:
        self.count = count
        self.interval_ms = interval_ms
        self.corrupt_every = corrupt_every
        self._rng = random.Random(seed)
        self._n = 0

    def readline(self) -> bytes:
        if self.count is not None and self._n >= self.count:
            return b""
        self._n += 1
        t = self._n * self.interval_ms
        phase = 2 * math.pi * t / 60000
        temp = 22.0 + 3.0 * math.sin(phase) + self._rng.gauss(0, 0.1)
        hum = 45.0 + 8.0 * math.cos(phase) + self._rng.gauss(0, 0.3)
        line = format_line(t, {"temp_c": temp, "hum_pct": hum})
        if self.corrupt_every and self._n % self.corrupt_every == 0:
            line = line.replace("temp_c=", "temp_c=9", 1)
        return (line + "\n").encode("ascii")
