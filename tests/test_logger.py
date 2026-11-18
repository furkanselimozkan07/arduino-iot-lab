import io

import pytest

from iotlab.cli import run
from iotlab.logger import CsvLogger, list_log_files, read_log, read_logs
from iotlab.parser import Reading


def mk(ms, t=20.0, h=50.0):
    return Reading(ms, {"temp_c": t, "hum_pct": h})


def test_write_and_read_roundtrip(tmp_path):
    with CsvLogger(tmp_path) as log:
        for i in range(3):
            log.write(mk(i * 1000, 20 + i))
    files = list_log_files(tmp_path)
    assert [f.name for f in files] == ["readings-0001.csv"]
    assert files[0].read_text().splitlines()[0] == "ms,hum_pct,temp_c"
    rows = list(read_log(files[0]))
    assert [r.timestamp_ms for r in rows] == [0, 1000, 2000]
    assert rows[2].get("temp_c") == 22.0


def test_rotation_creates_multiple_self_contained_files(tmp_path):
    with CsvLogger(tmp_path, max_bytes=100) as log:
        for i in range(20):
            log.write(mk(i))
    files = list_log_files(tmp_path)
    assert len(files) > 1
    for f in files:
        assert f.read_text().startswith("ms,hum_pct,temp_c\n")
        assert f.stat().st_size <= 100
    assert [r.timestamp_ms for r in read_logs(tmp_path)] == list(range(20))


def test_resume_appends_to_existing_file(tmp_path):
    with CsvLogger(tmp_path) as log:
        log.write(mk(1))
    with CsvLogger(tmp_path) as log:
        log.write(mk(2))
    assert len(list_log_files(tmp_path)) == 1
    assert [r.timestamp_ms for r in read_logs(tmp_path)] == [1, 2]


def test_resume_with_new_columns_starts_new_file(tmp_path):
    with CsvLogger(tmp_path) as log:
        log.write(mk(1))
    with CsvLogger(tmp_path, columns=["lux"]) as log:
        log.write(Reading(2, {"lux": 300.0}))
    assert len(list_log_files(tmp_path)) == 2


def test_missing_and_extra_keys(tmp_path):
    with CsvLogger(tmp_path, columns=["temp_c", "hum_pct"]) as log:
        log.write(Reading(1, {"temp_c": 21.0, "extra": 9.0}))
    (r,) = read_logs(tmp_path)
    assert r.values == {"temp_c": 21.0}


def test_prefixes_are_independent(tmp_path):
    with CsvLogger(tmp_path, prefix="a") as la, CsvLogger(tmp_path, prefix="b") as lb:
        la.write(mk(1))
        lb.write(mk(2))
    assert len(read_logs(tmp_path, "a")) == 1
    assert read_logs(tmp_path, "b")[0].timestamp_ms == 2


def test_invalid_max_bytes(tmp_path):
    with pytest.raises(ValueError):
        CsvLogger(tmp_path, max_bytes=10)


def test_read_log_rejects_foreign_csv(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError):
        list(read_log(p))


def test_cli_logs_to_directory(tmp_path):
    out = io.StringIO()
    assert run(["--simulate", "--count", "5", "--log-dir", str(tmp_path / "logs")], out=out) == 0
    rows = read_logs(tmp_path / "logs")
    assert len(rows) == 5 and "temp_c" in rows[0].values
