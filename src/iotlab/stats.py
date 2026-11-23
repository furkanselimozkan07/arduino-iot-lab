"""Windowed statistics (min / max / mean / stdev) over sensor readings.

:class:`WindowAggregator` collects readings into *tumbling* windows (they do
not overlap) closed either after ``count`` readings or after ``span_ms``
milliseconds of device time. Every closed window yields a
:class:`WindowSummary` with a :class:`Summary` per sensor key. Time is taken
from the reading's own ``timestamp_ms`` so replaying a log gives the same
result as live data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

from .parser import Reading


@dataclass(frozen=True)
class Summary:
    """Descriptive statistics of a list of numbers."""

    count: int
    min: float
    max: float
    mean: float
    stdev: float  # population standard deviation

    def __str__(self) -> str:
        return (f"n={self.count} min={self.min:.2f} max={self.max:.2f} "
                f"mean={self.mean:.2f} sd={self.stdev:.2f}")


def summarize(values: Sequence[float]) -> Summary:
    """Summarize a non-empty sequence of numbers."""
    if not values:
        raise ValueError("cannot summarize an empty sequence")
    n = len(values)
    mean = math.fsum(values) / n
    var = math.fsum((v - mean) ** 2 for v in values) / n
    return Summary(n, min(values), max(values), mean, math.sqrt(var))


@dataclass(frozen=True)
class WindowSummary:
    """Statistics of every sensor key within one window."""

    start_ms: int
    end_ms: int
    readings: int
    stats: Dict[str, Summary]

    def format(self) -> str:
        head = f"# stats [{self.start_ms}..{self.end_ms} ms, {self.readings} readings]"
        lines = [f"{head}"] + [f"#   {k}: {s}" for k, s in sorted(self.stats.items())]
        return "\n".join(lines)


class WindowAggregator:
    """Group readings into tumbling windows and summarize each one.

    Give exactly one of ``count`` (readings per window) or ``span_ms``
    (window length in device milliseconds).
    """

    def __init__(self, count: Optional[int] = None, span_ms: Optional[int] = None) -> None:
        if (count is None) == (span_ms is None):
            raise ValueError("specify exactly one of count or span_ms")
        if count is not None and count < 1:
            raise ValueError("count must be >= 1")
        if span_ms is not None and span_ms < 1:
            raise ValueError("span_ms must be >= 1")
        self.count = count
        self.span_ms = span_ms
        self._buf: List[Reading] = []
        self._window_start: Optional[int] = None

    def add(self, reading: Reading) -> Optional[WindowSummary]:
        """Add a reading; return the summary of a window if this closed one."""
        closed: Optional[WindowSummary] = None
        if self.span_ms is not None:
            if self._window_start is None:
                self._window_start = reading.timestamp_ms
            elif reading.timestamp_ms - self._window_start >= self.span_ms:
                closed = self.flush()
                # skip empty windows if the device was silent for a while
                gaps = (reading.timestamp_ms - self._window_start) // self.span_ms
                self._window_start += gaps * self.span_ms
            self._buf.append(reading)
            return closed
        self._buf.append(reading)
        if len(self._buf) >= (self.count or 1):
            return self.flush()
        return None

    def flush(self) -> Optional[WindowSummary]:
        """Close the current (possibly partial) window; None if it is empty."""
        if not self._buf:
            return None
        buf, self._buf = self._buf, []
        if self.span_ms is not None:
            self._window_start = (self._window_start or 0) + self.span_ms
        series: Dict[str, List[float]] = {}
        for r in buf:
            for key, value in r.values.items():
                series.setdefault(key, []).append(value)
        return WindowSummary(
            start_ms=buf[0].timestamp_ms,
            end_ms=buf[-1].timestamp_ms,
            readings=len(buf),
            stats={k: summarize(v) for k, v in series.items()},
        )

    def process(self, readings: Iterable[Reading]) -> Iterator[WindowSummary]:
        """Summaries for a whole stream, including the final partial window."""
        for r in readings:
            done = self.add(r)
            if done:
                yield done
        tail = self.flush()
        if tail:
            yield tail
