import io
import json

import pytest

from iotlab import Ema, HampelFilter, MovingAverage, Reading, ReadingFilter
from iotlab.cli import run


def test_moving_average_warmup_and_window():
    ma = MovingAverage(3)
    assert [ma.update(x) for x in (3, 6, 9, 12)] == [3, 4.5, 6, 9]


def test_moving_average_reset_and_validation():
    ma = MovingAverage(2)
    ma.update(10)
    ma.reset()
    assert ma.update(4) == 4
    with pytest.raises(ValueError):
        MovingAverage(0)


def test_ema():
    e = Ema(0.5)
    assert e.update(10) == 10
    assert e.update(20) == 15
    assert e.update(20) == 17.5
    with pytest.raises(ValueError):
        Ema(0)
    with pytest.raises(ValueError):
        Ema(1.5)


def test_hampel_replaces_spike_with_median():
    h = HampelFilter(window=5)
    out = [h.update(v) for v in (20.0, 20.1, 19.9, 20.0, 20.2)]
    assert out == [20.0, 20.1, 19.9, 20.0, 20.2]
    assert not h.last_was_outlier
    assert h.update(85.0) == pytest.approx(20.0)
    assert h.last_was_outlier
    assert h.update(20.1) == 20.1
    assert not h.last_was_outlier


def test_hampel_flat_signal_and_jump():
    h = HampelFilter()
    for _ in range(5):
        assert h.update(50.0) == 50.0
    assert h.update(70.0) == 50.0 and h.last_was_outlier


def test_hampel_validation():
    with pytest.raises(ValueError):
        HampelFilter(window=2)
    with pytest.raises(ValueError):
        HampelFilter(n_sigmas=0)


def test_reading_filter_per_key_and_skip():
    rf = ReadingFilter(lambda: MovingAverage(2), skip=("pressure",))
    r1 = rf.apply(Reading(0, {"temp_c": 10.0, "pressure": 1000.0}))
    r2 = rf.apply(Reading(1, {"temp_c": 20.0, "pressure": 900.0}))
    assert r1.values == {"temp_c": 10.0, "pressure": 1000.0}
    assert r2.values == {"temp_c": 15.0, "pressure": 900.0}
    assert r2.timestamp_ms == 1


def test_reading_filter_counts_outliers():
    rf = ReadingFilter(HampelFilter)
    for v in (20, 20.1, 19.9, 20.0):
        rf.apply(Reading(0, {"t": v}))
    rf.apply(Reading(0, {"t": 99.0}))
    assert rf.outliers == 1


def _lines(args):
    out = io.StringIO()
    assert run(args, out=out) == 0
    return out.getvalue().strip().splitlines()


def test_cli_smooth_reduces_spread():
    base = ["--simulate", "--count", "30", "--format", "json", "--seed", "1"]
    raw = [json.loads(l)["temp_c"] for l in _lines(base)]
    smooth = [json.loads(l)["temp_c"] for l in _lines(base + ["--smooth", "5"])]
    assert len(raw) == len(smooth) == 30
    assert smooth != raw
    assert max(smooth) - min(smooth) < max(raw) - min(raw)


def test_cli_filter_options_validated():
    assert run(["--simulate", "--smooth", "3", "--ema", "0.5"]) == 2
    assert run(["--simulate", "--ema", "2"]) == 2
    assert run(["--simulate", "--smooth", "-1"]) == 2


def test_cli_ema_and_outliers_run():
    assert len(_lines(["--simulate", "--count", "5", "--ema", "0.4", "--reject-outliers"])) == 5
