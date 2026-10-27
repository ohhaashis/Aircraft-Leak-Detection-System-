/*
 * Group 32 - Aircraft Hydraulic Leak Detection - ESP32 Data Acquisition Firmware (v2)
 * -----------------------------------------------------------------------------------
 * Reads:
 *   - 2x HK2016 pressure sensors (0-1 MPa, 0.5-4.5 V) via ADS1115 (I2C), through 10k/20k dividers
 *   - 5 V sensor rail via ADS1115 A2 (same divider) for ratiometric correction
 *   - 2x OF06ZAT flow sensors (NPN pulse) via GPIO interrupts (period measurement)
 *   - 36 acoustic-emission (AE) features from the STM32 over UART2 (GPIO16 RX)
 *
 * Sends one CSV row every 100 ms over USB serial (115200 baud), 43 columns:
 *   t_ms,P1,P2,Q1,Q2,C1,C2, AE1_rms..AE1_fdom, ..., AE4_rms..AE4_fdom
 *
 * STM32 line format (230400 baud, one line per 100 ms):
 *   $AE,<seq>,<36 comma-separated values>\n   (channel 1 features 1-9, then channel 2, ...)
 * If no STM32 line arrives for 1 s, the AE columns are sent as 0 and a warning line is printed.
 *
 * Serial commands:  Z = tare pressure (pump OFF)   K,<ch>,<val> = flow K-factor (Hz per L/min)
 *                   A1 / A0 = buzzer on / off (sent by the dashboard)
 *
 * Library: "Adafruit ADS1X15" (Arduino Library Manager). Board: ESP32 Dev Module.
 */

#include <Wire.h>
#include <Adafruit_ADS1X15.h>

// ------------------------- PIN MAP -------------------------
const int PIN_FLOW1 = 25;      // OF06ZAT #1 (inlet)  yellow wire, 10k pull-up to 3.3 V, 1k + cap filter
const int PIN_FLOW2 = 26;      // OF06ZAT #2 (outlet)
const int PIN_STM_RX = 16;     // UART2 RX  <- STM32 PA9 (TX)
const int PIN_STM_TX = 17;     // UART2 TX  -> STM32 PA10 (RX), optional (for commands)
const int PIN_LED = 2;
const int PIN_BUZZ = 27;       // optional buzzer via NPN transistor
// I2C: SDA = 21, SCL = 22

// ------------------------- CONSTANTS -------------------------
const float DIVIDER_GAIN = 20.0f / (10.0f + 20.0f);   // 10k top, 20k bottom
const uint32_t REPORT_MS = 100;
const uint32_t FLOW_TIMEOUT_US = 3000000;
const uint32_t AE_STALE_MS = 1000;
const int N_AE = 36;

// Flow K-factor (Hz per L/min). Datasheet value 1.2 is for WATER - calibrate with oil!
volatile float flowK[2] = {1.2f, 1.2f};

// ------------------------- GLOBALS -------------------------
Adafruit_ADS1115 ads;
bool adsOk = false;

volatile uint32_t flowLastUs[2] = {0, 0};
volatile uint32_t flowPeriodUs[2] = {0, 0};
volatile uint32_t flowCount[2] = {0, 0};

void IRAM_ATTR flowIsr1() {
  uint32_t now = micros(), dt = now - flowLastUs[0];
  if (dt > 2000) { flowPeriodUs[0] = dt; flowLastUs[0] = now; flowCount[0]++; }   // 2 ms debounce
}
void IRAM_ATTR flowIsr2() {
  uint32_t now = micros(), dt = now - flowLastUs[1];
  if (dt > 2000) { flowPeriodUs[1] = dt; flowLastUs[1] = now; flowCount[1]++; }
}

int adsChannel = 0;                 // 0 = P1, 1 = P2, 2 = 5 V rail
float vSensor[3] = {0, 0, 5.0f};
double pSum[2] = {0, 0};
uint32_t pN[2] = {0, 0};
float pZero[2] = {0, 0};

float ae[N_AE];                     // latest AE features from STM32
uint32_t aeLastMs = 0;
bool aeWarned = false;
String stmBuf, cmdBuf;
uint32_t lastReportMs = 0;

float voltsToKpa(float vout, float vcc) {          // HK2016: Vout = Vcc*(0.8*P + 0.1), P in MPa
  if (vcc < 4.0f) vcc = 5.0f;
  return ((vout / vcc) - 0.1f) / 0.8f * 1000.0f;
}

void startAds(int ch) {
  ads.startADCReading(ADS1X15_REG_CONFIG_MUX_SINGLE_0 + (ch << 12), false);
}

void parseStmLine(const String &line) {
  if (!line.startsWith("$AE,")) return;
  int idx = line.indexOf(',', 4);                  // skip "$AE,<seq>,"
  if (idx < 0) return;
  float vals[N_AE];
  int n = 0, start = idx + 1;
  while (n < N_AE && start <= (int)line.length()) {
    int comma = line.indexOf(',', start);
    if (comma < 0) comma = line.length();
    vals[n++] = line.substring(start, comma).toFloat();
    start = comma + 1;
  }
  if (n == N_AE) {
    memcpy(ae, vals, sizeof(ae));
    aeLastMs = millis();
    aeWarned = false;
  }
}

void handleCommand(String c) {
  c.trim();
  if (c.length() == 0) return;
  if (c == "Z") {
    for (int i = 0; i < 2; i++) pZero[i] = voltsToKpa(vSensor[i], vSensor[2]);
    Serial.printf("# TARE done. P zero: %.1f %.1f kPa\n", pZero[0], pZero[1]);
    Serial2.println("Z");                          // also ask STM32 to tare its AE baseline
    return;
  }
  if (c == "A1") { digitalWrite(PIN_BUZZ, HIGH); return; }
  if (c == "A0") { digitalWrite(PIN_BUZZ, LOW); return; }
  int p1 = c.indexOf(','), p2 = c.indexOf(',', p1 + 1);
  if (c.charAt(0) == 'K' && p1 > 0 && p2 > 0) {
    int ch = c.substring(p1 + 1, p2).toInt();
    float val = c.substring(p2 + 1).toFloat();
    if (ch >= 1 && ch <= 2 && val > 0) { flowK[ch - 1] = val; Serial.printf("# Flow%d K = %.4f\n", ch, val); return; }
  }
  Serial.println("# ? unknown command");
}

float flowLpm(int i) {
  noInterrupts();
  uint32_t period = flowPeriodUs[i], last = flowLastUs[i];
  interrupts();
  if (period == 0 || (micros() - last) > FLOW_TIMEOUT_US) return 0.0f;
  return (1e6f / period) / flowK[i];
}

void setup() {
  Serial.begin(115200);
  Serial2.begin(230400, SERIAL_8N1, PIN_STM_RX, PIN_STM_TX);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_BUZZ, OUTPUT);
  pinMode(PIN_FLOW1, INPUT);       // external 10k pull-up to 3.3 V
  pinMode(PIN_FLOW2, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_FLOW1), flowIsr1, FALLING);
  attachInterrupt(digitalPinToInterrupt(PIN_FLOW2), flowIsr2, FALLING);

  Wire.begin(21, 22);
  Wire.setClock(400000);
  adsOk = ads.begin(0x48);
  if (adsOk) {
    ads.setGain(GAIN_ONE);                 // +/-4.096 V full scale
    ads.setDataRate(RATE_ADS1115_475SPS);  // ~158 Hz per channel over 3 channels
    startAds(adsChannel);
  } else {
    Serial.println("# ERROR: ADS1115 not found - check SDA/SCL/ADDR wiring");
  }
  memset(ae, 0, sizeof(ae));
  delay(200);
  Serial.println("# Group32 leak DAQ v2 ready. Send Z with pump OFF to tare.");
  Serial.print("t_ms,P1,P2,Q1,Q2,C1,C2");
  const char *f[9] = {"rms", "peak", "p2p", "std", "energy", "crest", "hits", "dur", "fdom"};
  for (int ch = 1; ch <= 4; ch++) for (int k = 0; k < 9; k++) Serial.printf(",AE%d_%s", ch, f[k]);
  Serial.println();
  lastReportMs = millis();
}

void loop() {
  // 1) Pressure via ADS1115 (non-blocking round robin)
  if (adsOk && ads.conversionComplete()) {
    float vAdc = ads.computeVolts(ads.getLastConversionResults());
    vSensor[adsChannel] = vAdc / DIVIDER_GAIN;
    if (adsChannel < 2) {
      pSum[adsChannel] += voltsToKpa(vSensor[adsChannel], vSensor[2]) - pZero[adsChannel];
      pN[adsChannel]++;
    }
    adsChannel = (adsChannel + 1) % 3;
    startAds(adsChannel);
  }

  // 2) STM32 AE lines
  while (Serial2.available()) {
    char ch = Serial2.read();
    if (ch == '\n') { parseStmLine(stmBuf); stmBuf = ""; }
    else if (ch != '\r' && stmBuf.length() < 600) stmBuf += ch;
  }

  // 3) Report every 100 ms
  uint32_t nowMs = millis();
  if (nowMs - lastReportMs >= REPORT_MS) {
    lastReportMs += REPORT_MS;
    float p[2];
    for (int i = 0; i < 2; i++) { p[i] = pN[i] ? pSum[i] / pN[i] : 0; pSum[i] = 0; pN[i] = 0; }
    noInterrupts();
    uint32_t c1 = flowCount[0], c2 = flowCount[1];
    interrupts();
    bool aeOk = (nowMs - aeLastMs) < AE_STALE_MS;
    if (!aeOk && !aeWarned) { Serial.println("# WARNING: no AE data from STM32 (check PA9->GPIO16, GND)"); aeWarned = true; }

    Serial.printf("%lu,%.2f,%.2f,%.3f,%.3f,%lu,%lu", nowMs, p[0], p[1], flowLpm(0), flowLpm(1), c1, c2);
    for (int k = 0; k < N_AE; k++) Serial.printf(",%.2f", aeOk ? ae[k] : 0.0f);
    Serial.println();
    digitalWrite(PIN_LED, (nowMs / 500) % 2);
  }

  // 4) Commands from the laptop
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') { handleCommand(cmdBuf); cmdBuf = ""; }
    else cmdBuf += ch;
  }
}
