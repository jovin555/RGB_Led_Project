#include <Arduino.h>

void setup() {
  Serial.begin(115200);
  // Native USB CDC: give the host a moment to open the port so the first lines aren't lost.
  unsigned long t0 = millis();
  while (!Serial && millis() - t0 < 3000) delay(10);
  Serial.println("Hello, world! (ESP32-S3 LED controller)");
}

void loop() {
  static uint32_t n = 0;
  Serial.printf("Hello, world! #%lu  uptime %lu ms\n", (unsigned long)n++, (unsigned long)millis());
  delay(1000);
}
