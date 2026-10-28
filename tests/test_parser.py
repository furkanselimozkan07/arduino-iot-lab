import pytest

from iotlab import ParseError, SerialReader, SimulatedSerial, checksum, format_line, parse_line


def test_checksum_known_value():
    assert checksum("A") == 0x41
    assert checksum("AB") == 0x41 ^ 0x42


def test_roundtrip():
    line = format_line(1234, {"temp_c": 23.5, "hum_pct": 45.2})
    r = parse_line(line + "\r\n")
    assert r.timestamp_ms == 1234
    assert r.values == {"temp_c": 23.5, "hum_pct": 45.2}
    assert r.get("missing") is None


def test_documented_example_checksum():
    payload = "ms=1234,temp_c=23.50,hum_pct=45.20"
    assert parse_line(f"${payload}*{checksum(payload):02X}").get("temp_c") == 23.5


@pytest.mark.parametrize("line", [
    "ms=1,t=2*00",                      # no start marker
    "$ms=1,t=2",                        # no checksum
    "$ms=1,t=2*ZZ",                     # bad hex
    "$ms=1,t=2*00",                     # wrong checksum
    "",
])
def test_rejects_bad_frames(line):
    with pytest.raises(ParseError):
        parse_line(line)


def _frame(payload: str) -> str:
    return f"${payload}*{checksum(payload):02X}"


@pytest.mark.parametrize("payload", ["ms=1,t=abc", "ms=1,t", "t=2.0", "ms=1,=3"])
def test_rejects_bad_payload(payload):
    with pytest.raises(ParseError):
        parse_line(_frame(payload))


def test_corrupted_character_detected():
    line = format_line(10, {"temp_c": 20.0})
    with pytest.raises(ParseError):
        parse_line(line.replace("20.00", "21.00"))


def test_reader_counts_good_and_bad():
    reader = SerialReader(SimulatedSerial(count=9, corrupt_every=3))
    readings = list(reader)
    assert len(readings) == 6
    assert (reader.good, reader.bad) == (6, 3)
    assert readings[0].timestamp_ms == 2000
    assert 15 < readings[0].values["temp_c"] < 30


def test_reader_stops_on_timeout():
    class Empty:
        def readline(self):
            return b""

    assert SerialReader(Empty()).read_one() is None


def test_reader_handles_garbage_bytes():
    class Garbage:
        lines = [b"\xff\xfe junk\n", (format_line(5, {"x": 1.0}) + "\n").encode(), b""]

        def readline(self):
            return self.lines.pop(0)

    reader = SerialReader(Garbage())
    assert [r.timestamp_ms for r in reader] == [5]
    assert reader.bad == 1
