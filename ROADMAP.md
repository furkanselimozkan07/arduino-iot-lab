# Roadmap

## Vision
A small, well-tested lab for Arduino sensor projects: C++ sketches that emit a
checksummed line protocol, and Python host tools that read it (real or
simulated serial), store it, publish it over MQTT and show it in a live
Streamlit dashboard. Everything on the Python side must run without hardware.

## Backlog
- [x] Project layout, line protocol parser, simulated serial reader, DHT22 sketch
- [ ] CLI `iotlab-read` to print readings from a port or `--simulate`
- [ ] CSV logger with rotation and a reader to load logs back
- [ ] Sketch: BMP280 pressure/temperature driver with the same protocol
- [ ] Sketch: LDR + PIR sensor sketch with threshold helpers
- [ ] Auto-detect serial port (list ports, pick Arduino by VID/PID)
- [ ] Reconnect logic for unplugged boards (backoff, tested with fake port)
- [ ] Moving average / outlier filter module
- [ ] MQTT publisher (paho-mqtt) with injectable client and tests
- [ ] Config file (TOML) for port, topics and sensors
- [ ] Bridge: serial -> MQTT command `iotlab-bridge`
- [ ] Streamlit dashboard: live line charts from simulated source
- [ ] Dashboard: read from CSV log / MQTT subscription
- [ ] Alert rules (e.g. temp > threshold) with debounce
- [ ] Downlink commands to Arduino (LED/relay) with ack frames
- [ ] Sketch: relay + LED actuator controlled by serial commands
- [ ] Statistics summary (min/max/mean per window)
- [ ] GitHub Actions: pytest + arduino-cli compile check
- [ ] Docs: wiring diagrams and protocol specification
- [ ] Docker compose: Mosquitto + bridge + dashboard

## Changelog
- 2026-10-28: Initial layout, `iotlab.parser` (checksummed `key=value` frames), `SerialReader`/`SimulatedSerial`, DHT22 sketch, pytest suite.
