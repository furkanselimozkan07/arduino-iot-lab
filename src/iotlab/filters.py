"""Streaming filters for noisy sensor values.

All filters are tiny stateful objects with an ``update(x) -> float`` method,
so they work on live serial data without buffering a whole log.

* :class:`MovingAverage` - simple sliding-window mean.
* :class:`Ema` - exponential moving average (``alpha`` in (0, 1]).
* :class:`HampelFilter` - median/MAD outlier detector; an outlier is replaced
  by the window median (the classic Hampel identifier).
* :class:`ReadingFilter` - applies a filter per key to whole :class:`Reading` s.
"""

from __future__ import annotations

from collections import deque
from statistics import median
from typing import Callable, Deque, Dict, Optional

from .parser import Reading

# Makes the MAD a consistent estimator of the std deviation for normal data.
MAD_SCALE = 1.4826


class MovingAverage:
    """Mean of the last ``window`` samples (fewer while warming up)."""

    def __init__(self, window: int = 5) -> None:
        if window < 1:
            raise ValueError("window must be >= 1")
        self.window = window
        self._buf: Deque[float] = deque(maxlen=window)

    def update(self, x: float) -> float:
        self._buf.append(x)
        return sum(self._buf) / len(self._buf)

    def reset(self) -> None:
        self._buf.clear()


class Ema:
    """Exponential moving average: ``y = alpha * x + (1 - alpha) * y_prev``."""

    def __init__(self, alpha: float = 0.3) -> None:
        if not 0 < alpha <= 1:
            raise ValueError("alpha must be in (0, 1]")
        self.alpha = alpha
        self._y: Optional[float] = None

    def update(self, x: float) -> float:
        self._y = x if self._y is None else self.alpha * x + (1 - self.alpha) * self._y
        return self._y

    def reset(self) -> None:
        self._y = None


class HampelFilter:
    """Replace outliers by the window median.

    A sample is an outlier when it deviates from the median of the previous
    ``window`` (already cleaned) samples by more than ``n_sigmas`` scaled MADs.
    Until ``min_samples`` samples were seen nothing is rejected.
    ``last_was_outlier`` tells the caller what happened to the last sample.
    """

    def __init__(self, window: int = 7, n_sigmas: float = 3.0, min_samples: int = 3) -> None:
        if window < 3:
            raise ValueError("window must be >= 3")
        if n_sigmas <= 0:
            raise ValueError("n_sigmas must be > 0")
        self.window = window
        self.n_sigmas = n_sigmas
        self.min_samples = max(3, min_samples)
        self._buf: Deque[float] = deque(maxlen=window)
        self.last_was_outlier = False

    def update(self, x: float) -> float:
        self.last_was_outlier = False
        out = x
        if len(self._buf) >= self.min_samples:
            med = median(self._buf)
            mad = median(abs(v - med) for v in self._buf) * MAD_SCALE
            # flat signal (mad == 0): floor the threshold relative to the level
            threshold = self.n_sigmas * max(mad, 1e-6 * max(1.0, abs(med)))
            if abs(x - med) > threshold:
                self.last_was_outlier = True
                out = med
        self._buf.append(out)
        return out

    def reset(self) -> None:
        self._buf.clear()
        self.last_was_outlier = False


class ReadingFilter:
    """Apply an independent filter instance to every key of a stream of readings.

    ``factory`` builds a fresh filter for each new key. Keys listed in
    ``skip`` pass through untouched. ``outliers`` counts replaced samples.
    """

    def __init__(self, factory: Callable[[], object], skip: tuple = ()) -> None:
        self._factory = factory
        self._skip = set(skip)
        self._filters: Dict[str, object] = {}
        self.outliers = 0

    def apply(self, reading: Reading) -> Reading:
        new: Dict[str, float] = {}
        for key, val in reading.values.items():
            if key in self._skip:
                new[key] = val
                continue
            f = self._filters.setdefault(key, self._factory())
            new[key] = f.update(val)  # type: ignore[attr-defined]
            if getattr(f, "last_was_outlier", False):
                self.outliers += 1
        return Reading(reading.timestamp_ms, new)
