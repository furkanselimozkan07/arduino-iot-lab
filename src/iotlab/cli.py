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

from .alerts import AlertEngine
from .filters import Ema, HampelFilter, MovingAverage, ReadingFilter
from .logger import CsvLogger
from .parser import Reading
from .stats import WindowAggregator
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
    p.add_argument("--log-dir", help="also append readings to rotating CSV files in this directory")
    p.add_argument("--log-prefix", default="readings", help="log file prefix (default 'readings')")
    p.add_argument("--max-log-bytes", type=int, default=1_000_000, help="rotate log files at this size")
    p.add_argument("--smooth", type=int, default=0, metavar="N", help="moving average over N samples")
    p.add_argument("--ema", type=float, default=0.0, metavar="ALPHA", help="exponential smoothing factor (0 < ALPHA <= 1)")
    p.add_argument("--reject-outliers", action="store_true", help="replace spikes by the window median (Hampel filter)")
    p.add_argument("--alert", action="append", default=[], metavar="RULE",
                   help="alert rule such as 'temp_c>30 for 3 clear 28' (repeatable); events go to stderr")
    p.add_argument("--stats", type=int, default=0, metavar="N",
                   help="print min/max/mean/stdev per sensor every N readings (to stderr)")
    p.add_argument("--stats-ms", type=int, default=0, metavar="MS",
                   help="like --stats but windows of MS device milliseconds")
    return p


def build_filters(args: argparse.Namespace) -> List[ReadingFilter]:
    """Filter chain requested on the command line (outliers first, then smoothing)."""
    chain: List[ReadingFilter] = []
    if args.reject_outliers:
        chain.append(ReadingFilter(HampelFilter))
    if args.smooth:
        chain.append(ReadingFilter(lambda: MovingAverage(args.smooth)))
    if args.ema:
        chain.append(ReadingFilter(lambda: Ema(args.ema)))
    return chain


def run(argv: Optional[Sequence[str]] = None, out: Optional[TextIO] = None,
        source: Optional[LineSource] = None) -> int:
    """Run the CLI. ``source`` lets tests inject a fake port. Returns the exit code."""
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    if args.count is not None and args.count < 1:
        print("error: --count must be >= 1", file=sys.stderr)
        return 2
    if args.smooth < 0 or not 0 <= args.ema <= 1:
        print("error: --smooth must be >= 0 and --ema within 0..1", file=sys.stderr)
        return 2
    if args.smooth and args.ema:
        print("error: use either --smooth or --ema, not both", file=sys.stderr)
        return 2
    if args.stats < 0 or args.stats_ms < 0 or (args.stats and args.stats_ms):
        print("error: use one of --stats N or --stats-ms MS (both >= 0)", file=sys.stderr)
        return 2
    aggregator = None
    if args.stats:
        aggregator = WindowAggregator(count=args.stats)
    elif args.stats_ms:
        aggregator = WindowAggregator(span_ms=args.stats_ms)
    filters = build_filters(args)
    try:
        alerts = AlertEngine.from_strings(args.alert)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
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
    logger = None
    if args.log_dir:
        try:
            logger = CsvLogger(args.log_dir, args.log_prefix, args.max_log_bytes)
        except (ValueError, OSError) as exc:
            print(f"error: cannot start logging: {exc}", file=sys.stderr)
            return 2
    printed = 0
    columns: List[str] = []
    writer_header_done = False
    try:
        for reading in reader:
            for f in filters:
                reading = f.apply(reading)
            if not columns:
                columns = sorted(reading.values)
            if args.fmt == "csv" and not writer_header_done:
                print(",".join(["ms"] + columns), file=out)
                writer_header_done = True
            print(format_reading(reading, args.fmt, columns), file=out)
            for event in alerts.update(reading):
                print(event, file=sys.stderr)
            if aggregator:
                summary = aggregator.add(reading)
                if summary:
                    print(summary.format(), file=sys.stderr)
            if logger:
                logger.write(reading)
            printed += 1
            if args.count is not None and printed >= args.count:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if aggregator:
            tail = aggregator.flush()
            if tail:
                print(tail.format(), file=sys.stderr)
        if logger:
            logger.close()
    print(f"# {reader.good} valid, {reader.bad} corrupted lines", file=sys.stderr)
    return 0


def main() -> None:  # pragma: no cover - thin wrapper
    sys.exit(run())


if __name__ == "__main__":  # pragma: no cover
    main()
