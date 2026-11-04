"""Command line interface: ``iotlab-read``.

Prints readings from a serial port or from the built-in simulator::

    iotlab-read --simulate --count 5
    iotlab-read --port /dev/ttyACM0 --baud 9600 --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional, Sequence, TextIO

from .parser import Reading
from .serial_source import LineSource, SerialReader, SimulatedSerial

FORMATS = ("table", "json", "csv")


def format_reading(reading: Reading, fmt: str, columns: Sequence[str]) -> str:
    """Render one reading as a single output line in the requested format."""
    if fmt == "json":
        return json.dumps({"ms": reading.timestamp_ms, **reading.values})
    if fmt == "csv":
        cells = [str(reading.timestamp_ms)] + [
            "" if reading.get(c) is None else f"{reading.get(c):.2f}" for c in columns
        ]
        return ",".join(cells)
    cells = [f"{reading.timestamp_ms:>10}"] + [
        f"{c}={reading.get(c):.2f}" if reading.get(c) is not None else f"{c}=-"
        for c in columns
    ]
    return "  ".join(cells)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="iotlab-read", description="Print sensor readings from Arduino or a simulator.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="serial port, e.g. /dev/ttyACM0 or COM3")
    src.add_argument("--simulate", action="store_true", help="use the built-in simulated board")
    p.add_argument("--baud", type=int, default=9600, help="baud rate (default 9600)")
    p.add_argument("--count", type=int, default=None, help="stop after N valid readings")
    p.add_argument("--format", choices=FORMATS, default="table", dest="fmt", help="output format")
    p.add_argument("--interval-ms", type=int, default=2000, help="simulated sample interval")
    p.add_argument("--corrupt-every", type=int, default=0, help="simulate a corrupted line every N lines")
    p.add_argument("--seed", type=int, default=0, help="simulator random seed")
    return p


def run(argv: Optional[Sequence[str]] = None, out: Optional[TextIO] = None,
        source: Optional[LineSource] = None) -> int:
    """Run the CLI. ``source`` lets tests inject a fake port. Returns the exit code."""
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    if args.count is not None and args.count < 1:
        print("error: --count must be >= 1", file=sys.stderr)
        return 2

    if source is None:
        if args.simulate:
            # one extra line per expected corruption so --count valid readings are reachable
            total = None if args.count is None else args.count + (
                args.count // max(args.corrupt_every, 1) + 1 if args.corrupt_every else 0)
            source = SimulatedSerial(count=total, interval_ms=args.interval_ms,
                                     corrupt_every=args.corrupt_every, seed=args.seed)
        else:
            try:
                source = SerialReader.open(args.port, args.baud).source
            except Exception as exc:  # serial.SerialException, ImportError, ...
                print(f"error: cannot open {args.port}: {exc}", file=sys.stderr)
                return 1

    reader = SerialReader(source)
    printed = 0
    columns: List[str] = []
    writer_header_done = False
    try:
        for reading in reader:
            if not columns:
                columns = sorted(reading.values)
            if args.fmt == "csv" and not writer_header_done:
                print(",".join(["ms"] + columns), file=out)
                writer_header_done = True
            print(format_reading(reading, args.fmt, columns), file=out)
            printed += 1
            if args.count is not None and printed >= args.count:
                break
    except KeyboardInterrupt:
        pass
    print(f"# {reader.good} valid, {reader.bad} corrupted lines", file=sys.stderr)
    return 0


def main() -> None:  # pragma: no cover - thin wrapper
    sys.exit(run())


if __name__ == "__main__":  # pragma: no cover
    main()
