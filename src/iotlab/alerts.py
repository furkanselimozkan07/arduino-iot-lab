"""Threshold alert rules with debounce and hysteresis.

A rule watches one sensor key. It *fires* only after the condition held for
``for_samples`` consecutive readings (debounce, like the ``for:`` clause of
Prometheus alerting rules) and *resolves* once the value is back on the safe
side of the ``clear`` level for ``clear_samples`` consecutive readings
(hysteresis, so a value hovering around the threshold does not flap).

Rule syntax understood by :func:`parse_rule`::

    temp_c>30                     fire at once when temp_c > 30
    temp_c>30 for 3               ... after 3 consecutive samples
    temp_c>30 for 3 clear 28      ... and resolve only when temp_c <= 28
    hum_pct<20 for 2 clear 25     works for "<" / "<=" / ">=" too
"""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional

from .parser import Reading

_OPS: Dict[str, Callable[[float, float], bool]] = {
    ">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le,
}
_RULE_RE = re.compile(
    r"^\s*(?P<key>\w+)\s*(?P<op>>=|<=|>|<)\s*(?P<thr>-?\d+(?:\.\d+)?)"
    r"(?:\s+for\s+(?P<for>\d+))?"
    r"(?:\s+clear\s+(?P<clear>-?\d+(?:\.\d+)?))?\s*$"
)


@dataclass(frozen=True)
class AlertEvent:
    """State change emitted by :class:`AlertEngine`."""

    rule: str
    state: str  # "firing" or "resolved"
    value: float
    timestamp_ms: int

    def __str__(self) -> str:
        return f"[{self.state.upper()}] {self.rule} (value={self.value:.2f}, t={self.timestamp_ms}ms)"


class AlertRule:
    """One threshold condition plus its debounce state."""

    def __init__(self, key: str, op: str, threshold: float, for_samples: int = 1,
                 clear: Optional[float] = None, clear_samples: int = 1) -> None:
        if op not in _OPS:
            raise ValueError(f"unsupported operator {op!r}")
        if for_samples < 1 or clear_samples < 1:
            raise ValueError("for_samples and clear_samples must be >= 1")
        if clear is not None:
            # the clear level must lie on the safe side of the threshold
            if op in (">", ">=") and clear > threshold:
                raise ValueError("clear level must be <= threshold for '>' rules")
            if op in ("<", "<=") and clear < threshold:
                raise ValueError("clear level must be >= threshold for '<' rules")
        self.key, self.op, self.threshold = key, op, threshold
        self.for_samples, self.clear, self.clear_samples = for_samples, clear, clear_samples
        self.firing = False
        self._streak = 0

    @property
    def name(self) -> str:
        return f"{self.key}{self.op}{self.threshold:g}"

    def _violated(self, value: float) -> bool:
        return _OPS[self.op](value, self.threshold)

    def _recovered(self, value: float) -> bool:
        if self.clear is None:
            return not self._violated(value)
        # safe side of the clear level (inclusive)
        return value <= self.clear if self.op in (">", ">=") else value >= self.clear

    def update(self, reading: Reading) -> Optional[AlertEvent]:
        """Feed one reading; return an event only on a state change."""
        value = reading.get(self.key)
        if value is None:  # sensor missing from this frame: keep state
            return None
        if not self.firing:
            self._streak = self._streak + 1 if self._violated(value) else 0
            if self._streak >= self.for_samples:
                self.firing, self._streak = True, 0
                return AlertEvent(self.name, "firing", value, reading.timestamp_ms)
        else:
            self._streak = self._streak + 1 if self._recovered(value) else 0
            if self._streak >= self.clear_samples:
                self.firing, self._streak = False, 0
                return AlertEvent(self.name, "resolved", value, reading.timestamp_ms)
        return None


def parse_rule(text: str) -> AlertRule:
    """Build an :class:`AlertRule` from the textual syntax in the module docstring."""
    m = _RULE_RE.match(text)
    if not m:
        raise ValueError(f"invalid alert rule {text!r} (expected e.g. 'temp_c>30 for 3 clear 28')")
    return AlertRule(
        m["key"], m["op"], float(m["thr"]),
        for_samples=int(m["for"]) if m["for"] else 1,
        clear=float(m["clear"]) if m["clear"] else None,
    )


class AlertEngine:
    """Evaluates several rules against a stream of readings."""

    def __init__(self, rules: Iterable[AlertRule]) -> None:
        self.rules: List[AlertRule] = list(rules)

    @classmethod
    def from_strings(cls, specs: Iterable[str]) -> "AlertEngine":
        return cls(parse_rule(s) for s in specs)

    def update(self, reading: Reading) -> List[AlertEvent]:
        events = (r.update(reading) for r in self.rules)
        return [e for e in events if e is not None]

    @property
    def active(self) -> List[str]:
        return [r.name for r in self.rules if r.firing]
