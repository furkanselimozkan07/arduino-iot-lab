"""CSV logging with size-based rotation, plus a reader to load logs back.

Files are named ``<prefix>-0001.csv``, ``<prefix>-0002.csv`` ... inside a
directory. Each file starts with a header (``ms`` followed by the sensor
columns), so every file is self-contained. The column set is fixed by the first
reading (or given explicitly); unknown keys in later readings are ignored and
missing ones are written as empty cells.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, TextIO, Union

from .parser import Reading

PathLike = Union[str, Path]


def list_log_files(directory: PathLike, prefix: str = "readings") -> List[Path]:
    """Return the rotated log files of ``prefix`` sorted by sequence number."""
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)\.csv$")
    found = []
    for path in Path(directory).glob(f"{prefix}-*.csv"):
        m = pattern.match(path.name)
        if m:
            found.append((int(m.group(1)), path))
    return [p for _, p in sorted(found)]


class CsvLogger:
    """Append readings to rotating CSV files.

    Args:
        directory: where to write; created if missing.
        prefix: file name prefix.
        max_bytes: start a new file once the current one would exceed this size.
        columns: sensor columns; inferred from the first reading when ``None``.
    """

    def __init__(self, directory: PathLike, prefix: str = "readings",
                 max_bytes: int = 1_000_000, columns: Optional[Sequence[str]] = None) -> None:
        if max_bytes < 64:
            raise ValueError("max_bytes must be >= 64")
        self.directory = Path(directory)
        self.prefix = prefix
        self.max_bytes = max_bytes
        self.columns: Optional[List[str]] = list(columns) if columns is not None else None
        self.directory.mkdir(parents=True, exist_ok=True)
        self._fh: Optional[TextIO] = None
        self._writer = None
        self._index = 0
        self._size = 0
        existing = list_log_files(self.directory, prefix)
        if existing:  # resume: continue the newest file if its header matches
            last = existing[-1]
            self._index = int(last.stem.rsplit("-", 1)[1])
            header = _read_header(last)
            if header and self.columns is None:
                self.columns = header[1:]
            if header == ["ms"] + (self.columns or []):
                self._open(last, append=True)

    @property
    def current_path(self) -> Optional[Path]:
        return Path(self._fh.name) if self._fh else None

    def _path_for(self, index: int) -> Path:
        return self.directory / f"{self.prefix}-{index:04d}.csv"

    def _open(self, path: Path, append: bool) -> None:
        self._fh = open(path, "a" if append else "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._fh, lineterminator="\n")
        self._size = path.stat().st_size if append else 0
        if not append or self._size == 0:
            self._write_row(["ms"] + list(self.columns or []))

    def _write_row(self, row: Sequence[str]) -> None:
        line = ",".join(row) + "\n"  # size estimate; csv.writer quotes nothing numeric
        self._writer.writerow(row)
        self._size += len(line.encode("utf-8"))

    def _rotate(self) -> None:
        self.close()
        self._index += 1
        self._open(self._path_for(self._index), append=False)

    def write(self, reading: Reading) -> None:
        if self.columns is None:
            self.columns = sorted(reading.values)
        row = [str(reading.timestamp_ms)] + [
            "" if reading.get(c) is None else f"{reading.get(c):.2f}" for c in self.columns
        ]
        est = len((",".join(row) + "\n").encode("utf-8"))
        if self._fh is None:
            self._index += 1
            self._open(self._path_for(self._index), append=False)
        elif self._size + est > self.max_bytes and self._size > 0:
            self._rotate()
        self._write_row(row)
        self._fh.flush()

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "CsvLogger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _read_header(path: Path) -> List[str]:
    with open(path, newline="", encoding="utf-8") as fh:
        return next(csv.reader(fh), [])


def read_log(path: PathLike) -> Iterator[Reading]:
    """Yield readings from one CSV file written by :class:`CsvLogger`."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or reader.fieldnames[0] != "ms":
            raise ValueError(f"{path}: not an iotlab log (first column must be 'ms')")
        for row in reader:
            ms = int(row.pop("ms"))
            values = {k: float(v) for k, v in row.items() if v not in ("", None)}
            yield Reading(timestamp_ms=ms, values=values)


def read_logs(directory: PathLike, prefix: str = "readings") -> List[Reading]:
    """Load every rotated file of ``prefix`` in order into one list."""
    out: List[Reading] = []
    for path in list_log_files(directory, prefix):
        out.extend(read_log(path))
    return out


def log_readings(readings: Iterable[Reading], logger: CsvLogger) -> int:
    """Write all readings; returns how many were logged."""
    n = 0
    for r in readings:
        logger.write(r)
        n += 1
    return n
