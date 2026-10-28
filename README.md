# arduino-iot-lab

Arduino sensor projects (C++ sketches) plus Python host tools: serial reading and
parsing, MQTT publishing and a Streamlit live dashboard (planned, see
[ROADMAP.md](ROADMAP.md)).

## Features
- `sketches/dht_serial` – DHT22 temperature/humidity sketch printing checksummed frames (wiring in the file header).
- `iotlab.parser` – parses and validates frames such as `$ms=1234,temp_c=23.50,hum_pct=45.20*5A`; the `*HH` suffix is the XOR checksum of the payload, so corrupted lines are dropped.
- `iotlab.SerialReader` – iterates valid readings from any `readline()` source and counts bad lines.
- `iotlab.SimulatedSerial` – fake port (sine wave + noise, optional corruption) so everything works without hardware.

## Install & test
```bash
pip install -e . pytest
pytest
```

## Usage
```python
from iotlab import SerialReader, SimulatedSerial

for reading in SerialReader(SimulatedSerial(count=3)):
    print(reading.timestamp_ms, reading.values)

# real hardware:
# reader = SerialReader.open("/dev/ttyACM0", 9600)
```

## License
MIT
