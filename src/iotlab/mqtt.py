"""MQTT publisher for sensor readings.

The publisher only needs an object with a paho-style
``publish(topic, payload, qos, retain)`` method, so tests (and users without a
broker) can inject a fake. :func:`make_paho_client` builds a real client lazily,
so ``paho-mqtt`` stays an optional dependency (``pip install .[mqtt]``).

Topic layout (``prefix`` defaults to ``iotlab``, ``device`` to ``arduino``)::

    iotlab/arduino/state          {"ms": 1234, "temp_c": 23.5, ...}   (JSON)
    iotlab/arduino/temp_c         23.5                                (per key)
    iotlab/arduino/status         online | offline                    (retained)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Optional, Protocol

from .parser import Reading


class MqttClientLike(Protocol):
    def publish(self, topic: str, payload: Any = None, qos: int = 0, retain: bool = False) -> Any: ...


@dataclass
class MqttConfig:
    host: str = "localhost"
    port: int = 1883
    prefix: str = "iotlab"
    device: str = "arduino"
    qos: int = 0
    retain_state: bool = False
    per_key: bool = True
    username: Optional[str] = None
    password: Optional[str] = None

    def __post_init__(self) -> None:
        if self.qos not in (0, 1, 2):
            raise ValueError("qos must be 0, 1 or 2")
        for name in ("prefix", "device"):
            value = getattr(self, name)
            if not value or any(c in value for c in "#+") or value.startswith("/") or value.endswith("/"):
                raise ValueError(f"invalid topic segment for {name}: {value!r}")


class MqttPublisher:
    """Publish :class:`Reading` objects as JSON and/or per-sensor topics."""

    def __init__(self, client: MqttClientLike, config: Optional[MqttConfig] = None) -> None:
        self.client = client
        self.config = config or MqttConfig()
        self.published = 0

    @property
    def base_topic(self) -> str:
        return f"{self.config.prefix}/{self.config.device}"

    def topic(self, suffix: str) -> str:
        return f"{self.base_topic}/{suffix}"

    def payload(self, reading: Reading) -> str:
        data = {"ms": reading.timestamp_ms, **reading.values}
        return json.dumps(data, separators=(",", ":"), sort_keys=False)

    def publish(self, reading: Reading) -> int:
        """Publish one reading; returns the number of MQTT messages sent."""
        cfg = self.config
        self.client.publish(self.topic("state"), self.payload(reading), qos=cfg.qos, retain=cfg.retain_state)
        sent = 1
        if cfg.per_key:
            for key, value in reading.values.items():
                self.client.publish(self.topic(key), repr(float(value)), qos=cfg.qos, retain=False)
                sent += 1
        self.published += sent
        return sent

    def publish_status(self, online: bool) -> None:
        """Retained availability message (use together with the will)."""
        self.client.publish(self.topic("status"), "online" if online else "offline", qos=1, retain=True)

    def publish_all(self, readings: Iterable[Reading]) -> Iterator[Reading]:
        """Publish each reading and yield it unchanged (handy in pipelines)."""
        for reading in readings:
            self.publish(reading)
            yield reading


def make_paho_client(config: MqttConfig, client_id: str = "iotlab-bridge") -> Any:
    """Create and connect a real paho-mqtt client with an offline last-will."""
    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("paho-mqtt is required: pip install 'arduino-iot-lab[mqtt]'") from exc
    if hasattr(mqtt, "CallbackAPIVersion"):  # paho-mqtt >= 2.0
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    else:  # pragma: no cover
        client = mqtt.Client(client_id=client_id)
    if config.username:
        client.username_pw_set(config.username, config.password)
    client.will_set(f"{config.prefix}/{config.device}/status", "offline", qos=1, retain=True)
    client.connect(config.host, config.port, keepalive=60)
    client.loop_start()
    return client
