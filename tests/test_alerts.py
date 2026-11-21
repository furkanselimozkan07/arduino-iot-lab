import pytest

from iotlab.alerts import AlertEngine, AlertRule, parse_rule
from iotlab.cli import run
from iotlab.parser import Reading


def feed(rule, values, key="temp_c"):
    events = []
    for i, v in enumerate(values):
        e = rule.update(Reading(i * 1000, {key: v}))
        if e:
            events.append((i, e.state))
    return events


def test_fires_immediately_by_default():
    assert feed(parse_rule("temp_c>30"), [29, 31, 32]) == [(1, "firing")]


def test_debounce_requires_consecutive_samples():
    r = parse_rule("temp_c>30 for 3")
    assert feed(r, [31, 31, 25, 31, 31, 31]) == [(5, "firing")]


def test_resolves_without_hysteresis():
    assert feed(parse_rule("temp_c>30"), [31, 30, 31]) == [
        (0, "firing"), (1, "resolved"), (2, "firing")]


def test_hysteresis_prevents_flapping():
    r = parse_rule("temp_c>30 for 1 clear 28")
    assert feed(r, [31, 29.5, 30.5, 28, 31]) == [(0, "firing"), (3, "resolved"), (4, "firing")]


def test_low_threshold_rule():
    r = parse_rule("hum_pct<20 for 2 clear 25")
    assert feed(r, [19, 18, 22, 25], key="hum_pct") == [(1, "firing"), (3, "resolved")]


def test_missing_key_is_ignored():
    r = parse_rule("temp_c>30")
    assert r.update(Reading(0, {"hum_pct": 50})) is None and not r.firing


def test_event_str_and_engine_active():
    eng = AlertEngine.from_strings(["temp_c>30", "hum_pct<20"])
    events = eng.update(Reading(5, {"temp_c": 35, "hum_pct": 50}))
    assert len(events) == 1 and "FIRING" in str(events[0]) and "temp_c>30" in str(events[0])
    assert eng.active == ["temp_c>30"]


@pytest.mark.parametrize("bad", ["", "temp_c=30", "temp_c>abc", "temp_c>30 for 0",
                                 "temp_c>30 clear 35", "hum<20 clear 10"])
def test_invalid_rules(bad):
    with pytest.raises(ValueError):
        parse_rule(bad)


def test_rule_validation():
    with pytest.raises(ValueError):
        AlertRule("t", "!=", 1)


def test_cli_alert_output(capsys):
    import io
    assert run(["--simulate", "--count", "30", "--alert", "temp_c>0"], out=io.StringIO()) == 0
    assert "[FIRING] temp_c>0" in capsys.readouterr().err


def test_cli_bad_alert(capsys):
    import io
    assert run(["--simulate", "--alert", "nonsense"], out=io.StringIO()) == 2
