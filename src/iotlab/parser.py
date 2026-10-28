"""Parser for the line protocol emitted by the Arduino sketches.

Wire format (one reading per line, ``\\n`` terminated)::

    $ms=1234,temp_c=23.50,hum_pct=45.2*5A

* The line starts with ``$``.
* The payload is a comma separated list of ``key=value`` pairs. ``ms`` is the
  Arduino ``millis()`` timestamp; all other values are floats.
* ``*HH`` is the XOR of every payload byte (between ``$`` and ``*``) as two
  upper-case hex digits. It lets the host drop lines corrupted on the wire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping


class ParseError(ValueError):
    """Raised when a line is not a valid sensor frame."""


@dataclass(frozen=True)
class Reading:
    """A single decoded frame."""

    timestamp_ms: int
    values: Dict[str, float] = field(default_factory=dict)

    def get(self, key: str, default: float | None = None) -> float | None:
        return self.values.get(key, default)


def checksum(payload: str) -> int:
    """XOR checksum of the payload bytes (matches the Arduino implementation)."""
    result = 0
    for byte in payload.encode("ascii"):
        result ^= byte
    return result


def format_line(timestamp_ms: int, values: Mapping[str, float]) -> str:
    """Build a frame exactly as the sketch does. Useful for simulation/tests."""
    parts = [f"ms={timestamp_ms}"] + [f"{k}={v:.2f}" for k, v in values.items()]
    payload = ",".join(parts)
    return f"${payload}*{checksum(payload):02X}"


def parse_line(line: str) -> Reading:
    """Decode one frame, validating the checksum.

    Raises:
        ParseError: on a missing marker/checksum, checksum mismatch, malformed
            pair, non-numeric value or missing ``ms`` timestamp.
    """
    line = line.strip()
    if not line.startswith("$"):
        raise ParseError(f"missing '$' start marker: {line!r}")
    body, sep, cs_text = line[1:].rpartition("*")
    if not sep:
        raise ParseError(f"missing '*' checksum separator: {line!r}")
    try:
        expected = int(cs_text, 16)
    except ValueError:
        raise ParseError(f"invalid checksum field {cs_text!r}") from None
    try:
        actual = checksum(body)
    except UnicodeEncodeError:
        raise ParseError("non-ASCII payload") from None
    if actual != expected:
        raise ParseError(f"checksum mismatch: expected {expected:02X}, got {actual:02X}")

    values: Dict[str, float] = {}
    for pair in body.split(","):
        key, eq, raw = pair.partition("=")
        if not eq or not key:
            raise ParseError(f"malformed pair {pair!r}")
        try:
            values[key] = float(raw)
        except ValueError:
            raise ParseError(f"non-numeric value in {pair!r}") from None
    if "ms" not in values:
        raise ParseError("frame has no 'ms' timestamp")
    timestamp = int(values.pop("ms"))
    return Reading(timestamp_ms=timestamp, values=values)
