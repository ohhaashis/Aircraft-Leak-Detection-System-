/*
 * AE protocol test for STM32F411 Black Pill (Arduino IDE + STM32duino core).
 * Sends FAKE "$AE,..." lines at 10 Hz on PA9 so the ESP32 merge and Python pipeline can be
 * tested before the real AE firmware exists. Not for experiments.
 *
 * Wiring: PA9 (TX) -> ESP32 GPIO16, GND -> ESP32 GND.
 * Optional: a potentiometer on PA1 (0-3.3 V) makes channel 1's "loudness" follow the knob,
 * so you can see the AE1 columns change on the laptop.
 */
HardwareSerial AeSerial(PA10, PA9);   // RX, TX (USART1)

uint32_t seq = 0, last = 0;

void setup() {
  AeSerial.begin(230400);
  pinMode(PA1, INPUT_ANALOG);
}

void loop() {
  if (millis() - last < 100) return;
  last += 100;
  float knob = analogRead(PA1) / 4.0f;            // 0..~1023
  AeSerial.print("$AE,");
  AeSerial.print(seq++);
  for (int ch = 1; ch <= 4; ch++) {
    float rms = (ch == 1 ? 20 + knob : 20 + 5 * ch) + random(0, 50) / 10.0f;
    float peak = rms * 2.5f;
    float vals[9] = {rms, peak, 1.8f * peak, 0.95f * rms, rms * rms * 0.1f,
                     peak / rms, (float)random(0, 4), (float)random(0, 30) / 10.0f,
                     40000.0f + random(-1000, 1000)};
    for (int k = 0; k < 9; k++) { AeSerial.print(','); AeSerial.print(vals[k], 2); }
  }
  AeSerial.println();
}
