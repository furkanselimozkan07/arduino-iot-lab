/*
 * dht_serial - read a DHT22 and print checksummed frames over Serial.
 *
 * Wiring (Arduino Uno):
 *   DHT22 pin 1 (VCC)  -> 5V
 *   DHT22 pin 2 (DATA) -> D2  (+ 10k pull-up resistor to 5V)
 *   DHT22 pin 4 (GND)  -> GND
 *
 * Library: "DHT sensor library" by Adafruit (+ Adafruit Unified Sensor).
 *
 * Output (9600 baud), one frame per interval, parsed by iotlab.parser:
 *   $ms=1234,temp_c=23.50,hum_pct=45.20*5A
 * The trailing hex byte is the XOR of all characters between '$' and '*'.
 */
#include <DHT.h>

const uint8_t  DHT_PIN = 2;
const uint32_t INTERVAL_MS = 2000;  // DHT22 needs >= 2 s between reads

DHT dht(DHT_PIN, DHT22);
uint32_t lastRead = 0;

// XOR of every character in `payload`.
uint8_t xorChecksum(const char *payload) {
  uint8_t cs = 0;
  while (*payload) cs ^= (uint8_t)*payload++;
  return cs;
}

// Build "ms=..,temp_c=..,hum_pct=.." into buf.
void buildPayload(char *buf, size_t size, uint32_t ms, float t, float h) {
  char ts[12], hs[12];
  dtostrf(t, 1, 2, ts);
  dtostrf(h, 1, 2, hs);
  snprintf(buf, size, "ms=%lu,temp_c=%s,hum_pct=%s", (unsigned long)ms, ts, hs);
}

void sendFrame(uint32_t ms, float t, float h) {
  char payload[64];
  buildPayload(payload, sizeof(payload), ms, t, h);
  char frame[80];
  snprintf(frame, sizeof(frame), "$%s*%02X", payload, xorChecksum(payload));
  Serial.println(frame);
}

void setup() {
  Serial.begin(9600);
  dht.begin();
}

void loop() {
  uint32_t now = millis();
  if (now - lastRead < INTERVAL_MS) return;
  lastRead = now;

  float h = dht.readHumidity();
  float t = dht.readTemperature();
  if (isnan(h) || isnan(t)) return;  // skip failed reads; host sees a gap
  sendFrame(now, t, h);
}
