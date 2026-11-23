import math

import pytest

from iotlab.parser import Reading
from iotlab.stats import WindowAggregator, summarize
from iotlab.cli import run


def R(ms, t, h=50.0):
    return Reading(ms, {"temp_c": t, "hum_pct": h})


def test_summarize_basic():
    s = summarize([1, 2, 3, 4])
    assert (s.count, s.min, s.max, s.mean) == (4, 1, 4, 2.5)
    assert s.stdev == pytest.approx(math.sqrt(1.25))


def test_summarize_single_and_empty():
    assert summarize([7]).stdev == 0
    with pytest.raises(ValueError):
        summarize([])


def test_count_windows():
    agg = WindowAggregator(count=3)
    out = [agg.add(R(i * 1000, float(i))) for i in range(7)]
    closed = [w for w in out if w]
    assert len(closed) == 2
    assert closed[0].stats["temp_c"].mean == 1.0
    assert (closed[0].start_ms, closed[0].end_ms) == (0, 2000)
    tail = agg.flush()
    assert tail.readings == 1 and tail.stats["temp_c"].min == 6.0
    assert agg.flush() is None


def test_time_windows_and_gap():
    agg = WindowAggregator(span_ms=10_000)
    wins = list(agg.process([R(0, 1), R(4000, 3), R(10_000, 5), R(52_000, 9), R(55_000, 11)]))
    assert [w.readings for w in wins] == [2, 1, 2]
    assert wins[0].stats["temp_c"].mean == 2
    assert wins[2].stats["temp_c"].max == 11


def test_missing_keys_summarized_separately():
    agg = WindowAggregator(count=2)
    agg.add(Reading(0, {"a": 1.0}))
    w = agg.add(Reading(1, {"a": 3.0, "b": 5.0}))
    assert w.stats["a"].count == 2 and w.stats["b"].count == 1


def test_invalid_config():
    for kwargs in ({}, {"count": 1, "span_ms": 5}, {"count": 0}, {"span_ms": 0}):
        with pytest.raises(ValueError):
            WindowAggregator(**kwargs)


def test_format_contains_keys():
    w = next(WindowAggregator(count=1).process([R(5, 20.0)]))
    text = w.format()
    assert "temp_c" in text and "hum_pct" in text and "1 readings" in text


def test_cli_stats(capsys):
    import io
    assert run(["--simulate", "--count", "5", "--stats", "2"], out=io.StringIO()) == 0
    err = capsys.readouterr().err
    assert err.count("# stats") == 3  # 2 + 2 + partial 1
    assert "mean=" in err


def test_cli_stats_ms_and_conflict(capsys):
    import io
    assert run(["--simulate", "--count", "6", "--stats-ms", "4000"], out=io.StringIO()) == 0
    assert "# stats" in capsys.readouterr().err
    assert run(["--simulate", "--stats", "2", "--stats-ms", "5"], out=io.StringIO()) == 2
