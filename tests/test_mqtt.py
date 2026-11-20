import json

import pytest

from iotlab import MqttConfig, MqttPublisher, Reading, SerialReader, SimulatedSerial


class FakeClient:
    def __init__(self):
        self.messages = []

    def publish(self, topic, payload=None, qos=0, retain=False):
        self.messages.append((topic, payload, qos, retain))


def make(**kw):
    client = FakeClient()
    return client, MqttPublisher(client, MqttConfig(**kw))


def test_publish_state_json_and_per_key():
    client, pub = make(qos=1)
    n = pub.publish(Reading(1234, {"temp_c": 23.5, "hum_pct": 40.0}))
    assert n == 3
    topic, payload, qos, retain = client.messages[0]
    assert topic == "iotlab/arduino/state"
    assert json.loads(payload) == {"ms": 1234, "temp_c": 23.5, "hum_pct": 40.0}
    assert qos == 1 and retain is False
    assert ("iotlab/arduino/temp_c", "23.5", 1, False) in client.messages
    assert pub.published == 3


def test_per_key_disabled_and_retain():
    client, pub = make(per_key=False, retain_state=True, prefix="lab", device="uno1")
    assert pub.publish(Reading(1, {"x": 1.0})) == 1
    assert client.messages == [("lab/uno1/state", '{"ms":1,"x":1.0}', 0, True)]


def test_status_is_retained():
    client, pub = make()
    pub.publish_status(True)
    pub.publish_status(False)
    assert client.messages == [
        ("iotlab/arduino/status", "online", 1, True),
        ("iotlab/arduino/status", "offline", 1, True),
    ]


def test_publish_all_passes_readings_through():
    client, pub = make(per_key=False)
    readings = list(pub.publish_all(SerialReader(SimulatedSerial(count=4))))
    assert len(readings) == 4
    assert len(client.messages) == 4


@pytest.mark.parametrize("kwargs", [{"qos": 3}, {"prefix": "a/#"}, {"device": ""}, {"prefix": "/x"}, {"device": "a+"}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        MqttConfig(**kwargs)
