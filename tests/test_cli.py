import io
import json

import pytest

from iotlab.cli import format_reading, run
from iotlab.parser import Reading, format_line


class FakePort:
    def __init__(self, lines):
        self.lines = [(l + "\n").encode() for l in lines]

    def readline(self):
        return self.lines.pop(0) if self.lines else b""


def test_simulate_table_count():
    out = io.StringIO()
    assert run(["--simulate", "--count", "3"], out=out) == 0
    lines = out.getvalue().strip().splitlines()
    assert len(lines) == 3
    assert "hum_pct=" in lines[0] and "temp_c=" in lines[0]


def test_simulate_json_is_valid():
    out = io.StringIO()
    run(["--simulate", "--count", "2", "--format", "json"], out=out)
    rows = [json.loads(l) for l in out.getvalue().splitlines()]
    assert rows[0]["ms"] == 2000 and "temp_c" in rows[0]


def test_csv_has_header():
    out = io.StringIO()
    run(["--simulate", "--count", "2", "--format", "csv"], out=out)
    lines = out.getvalue().splitlines()
    assert lines[0] == "ms,hum_pct,temp_c"
    assert len(lines) == 3


def test_corrupt_lines_skipped_and_counted(capsys):
    out = io.StringIO()
    run(["--simulate", "--count", "4", "--corrupt-every", "2"], out=out)
    assert len(out.getvalue().strip().splitlines()) == 4
    assert "corrupted" in capsys.readouterr().err


def test_injected_source_skips_garbage():
    port = FakePort(["garbage", format_line(10, {"t": 1.5}), format_line(20, {"t": 2.5})])
    out = io.StringIO()
    run(["--simulate"], out=out, source=port)
    assert len(out.getvalue().strip().splitlines()) == 2


def test_missing_column_rendered():
    r = Reading(5, {"a": 1.0})
    assert format_reading(r, "csv", ["a", "b"]) == "5,1.00,"
    assert "b=-" in format_reading(r, "table", ["a", "b"])


def test_bad_count_and_no_source():
    assert run(["--simulate", "--count", "0"]) == 2
    with pytest.raises(SystemExit):
        run([])


def test_unopenable_port(capsys):
    assert run(["--port", "/dev/does-not-exist"]) == 1
    assert "cannot open" in capsys.readouterr().err
