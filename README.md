# arduino-iot-lab

Arduino sensor projects (C++ sketches) plus Python host tools: serial reading and
parsing, MQTT publishing and a Streamlit live dashboard (planned, see
[ROADMAP.md](ROADMAP.md)).

## Features
- `sketches/dht_serial` – DHT22 temperature/humidity sketch printing checksummed frames (wiring in the file header).
- `iotlab.parser` – parses and validates frames such as `$ms=1234,temp_c=23.50,hum_pct=45.20*5A`; the `*HH` suffix is the XOR checksum of the payload, so corrupted lines are dropped.
- `iotlab.SerialReader` – iterates valid readings from any `readline()` source and counts bad lines.
- `iotlab.SimulatedSerial` – fake port (sine wave + noise, optional corruption) so everything works without hardware.

- `iotlab-read` – CLI printing readings from a port or the simulator as table, JSON lines or CSV.
- `iotlab.CsvLogger` – rotating CSV logs (`readings-0001.csv`, ...; each file has its own header, resumes on restart) and `read_log`/`read_logs` to load them back as `Reading`s.
- `iotlab.filters` – streaming `MovingAverage`, `Ema` and `HampelFilter` (median/MAD outlier replacement), applied per sensor key with `ReadingFilter`.
- `iotlab.MqttPublisher` – publishes readings as JSON (`iotlab/arduino/state`) and per-sensor topics, with retained `status` and an injectable client (fake in tests; `make_paho_client` for a real broker, `pip install .[mqtt]`).
- `iotlab.alerts` – threshold rules with debounce (`for N`) and hysteresis (`clear X`), e.g. `temp_c>30 for 3 clear 28`; `iotlab-read --alert RULE` prints FIRING/RESOLVED events to stderr. Debounce idea follows the `for:` clause of [Prometheus alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/).

## Install & test
```bash
pip install -e . pytest
pytest
```

## Usage
```bash
iotlab-read --simulate --count 5                 # no hardware needed
iotlab-read --port /dev/ttyACM0 --format json   # real board
iotlab-read --simulate --count 100 --log-dir logs --max-log-bytes 2000   # rotating CSV log
iotlab-read --simulate --count 50 --reject-outliers --smooth 5   # despike, then average
iotlab-read --simulate --alert 'temp_c>25 for 3 clear 24'   # debounced alert
```

```python
from iotlab import SerialReader, SimulatedSerial

for reading in SerialReader(SimulatedSerial(count=3)):
    print(reading.timestamp_ms, reading.values)

from iotlab import read_logs
print(len(read_logs("logs")), "readings loaded from logs/")

# real hardware:
# reader = SerialReader.open("/dev/ttyACM0", 9600)
```

## License
MIT
