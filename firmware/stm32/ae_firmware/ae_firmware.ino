/*
 * Group 32 - Aircraft Hydraulic Leak Detection - STM32F411 Acoustic-Emission (AE) firmware
 * -----------------------------------------------------------------------------------------
 * Board : WeAct STM32F411CEU6 "Black Pill"   (Arduino IDE + STM32duino core)
 *         Tools > Board: "Generic STM32F4 series", Board part number: "BlackPill F411CE"
 *         Tools > USB support: "CDC (generic 'Serial' supersede U(S)ART)"  (for USB debug output)
 *         Tools > Optimize: "Faster (-O2)"
 *
 * What it does:
 *   - Samples PA1..PA4 (4 AE channels) at 200 kHz each: TIM2 triggers an ADC1 scan of 4 channels,
 *     results go to a circular DMA buffer.
 *   - The DMA interrupt updates running statistics for every sample (RAM is too small to store
 *     100 ms of raw data) and captures the first 1024 samples of each channel for an FFT.
 *   - Every 100 ms the main loop computes 9 features per channel and sends ONE line to the ESP32:
 *       $AE,<seq>,<ch1: rms,peak,p2p,std,energy,crest,hits,dur,fdom>,<ch2...>,<ch3...>,<ch4...>
 *     on USART1 (PA9 TX -> ESP32 GPIO16) at 230400 baud. The same line is echoed to USB Serial.
 *   - Feature definitions match python/ae_reference.py exactly.
 *
 * Commands (from ESP32 on PA10, or typed in the USB Serial Monitor):
 *   Z            tare: average 1 s of samples per channel -> new baselines (pump OFF!)
 *   T,<ch>,<n>   set hit threshold of channel ch (1-4) to n ADC counts above baseline
 *   S            print status (sample rate, dropped blocks, baselines, thresholds)
 */

#include <math.h>

// ------------------------- SETTINGS -------------------------
#define FS_CH        200000UL         // samples per second per channel
#define N_CH         4
#define BLOCK_FRAMES 20000UL          // 100 ms per block
#define HALF_FRAMES  400              // frames per DMA half-buffer (2 ms)
#define FFT_N        1024
#define F_MIN_HZ     5000
#define HIT_DEAD     200              // samples below threshold that end a hit (1 ms)
#define ECHO_USB     1                // 1 = also print lines to USB Serial

#if defined(STM32_CORE_VERSION_MAJOR) && (STM32_CORE_VERSION_MAJOR >= 3)
Uart AeSerial(PA10, PA9);             // USART1: RX, TX (STM32duino core 3.x)
#else
HardwareSerial AeSerial(PA10, PA9);   // USART1: RX, TX (STM32duino core 2.x)
#endif

// ------------------------- HAL HANDLES -------------------------
ADC_HandleTypeDef hadc1;
DMA_HandleTypeDef hdma_adc1;
TIM_HandleTypeDef htim2;

// ------------------------- BUFFERS -------------------------
#define DMA_LEN (2 * HALF_FRAMES * N_CH)
static volatile uint16_t dmaBuf[DMA_LEN];
static int16_t cap[2][N_CH][FFT_N];           // double-buffered FFT capture
static float re[FFT_N], im[FFT_N], hann[FFT_N], cosT[FFT_N / 2], sinT[FFT_N / 2];

// ------------------------- STATISTICS -------------------------
struct Acc {
  int64_t sumsq;
  int32_t sum;
  uint32_t rawsum;
  int16_t maxv, minv, peak;
  uint16_t hits;
  uint32_t dur;
};
static volatile Acc acc[N_CH];
static Acc ready[N_CH];
static volatile bool readyFlag = false;
static volatile uint8_t capBuf = 0, readyCap = 0;
static volatile uint32_t blockFrames = 0, capN = 0, seq = 0, dropped = 0;
static bool inHit[N_CH];
static uint16_t belowCnt[N_CH];

static volatile int16_t baseline[N_CH] = {2048, 2048, 2048, 2048};
static volatile int16_t threshold[N_CH] = {150, 150, 150, 150};
static int tareBlocksLeft = 0;
static double tareSum[N_CH];

// ------------------------- DMA processing (runs in interrupt) -------------------------
static inline void resetAcc() {
  for (int c = 0; c < N_CH; c++) {
    acc[c].sumsq = 0; acc[c].sum = 0; acc[c].rawsum = 0;
    acc[c].maxv = -32768; acc[c].minv = 32767; acc[c].peak = 0;
    acc[c].hits = 0; acc[c].dur = 0;
    inHit[c] = false; belowCnt[c] = 0;
  }
}

static void processHalf(const volatile uint16_t *p) {
  for (int f = 0; f < HALF_FRAMES; f++) {
    for (int c = 0; c < N_CH; c++) {
      uint16_t s = p[f * N_CH + c];
      int16_t x = (int16_t)s - baseline[c];
      Acc &a = (Acc &)acc[c];
      a.sum += x;
      a.sumsq += (int32_t)x * x;
      a.rawsum += s;
      if (x > a.maxv) a.maxv = x;
      if (x < a.minv) a.minv = x;
      int16_t ax = x < 0 ? -x : x;
      if (ax > a.peak) a.peak = ax;
      if (ax > threshold[c]) {                 // hit detection with 1 ms dead time
        if (!inHit[c]) { a.hits++; inHit[c] = true; }
        a.dur++;
        belowCnt[c] = 0;
      } else if (inHit[c] && ++belowCnt[c] >= HIT_DEAD) {
        inHit[c] = false;
      }
      if (capN < FFT_N) cap[capBuf][c][capN] = x;
    }
    capN++;
  }
  blockFrames += HALF_FRAMES;
  if (blockFrames >= BLOCK_FRAMES) {           // 100 ms block finished
    if (readyFlag) dropped++;                  // main loop did not keep up
    for (int c = 0; c < N_CH; c++) ready[c] = (const Acc &)acc[c];
    readyCap = capBuf;
    capBuf ^= 1;
    capN = 0;
    blockFrames = 0;
    resetAcc();
    seq++;
    readyFlag = true;
  }
}

extern "C" void HAL_ADC_ConvHalfCpltCallback(ADC_HandleTypeDef *h) { processHalf(&dmaBuf[0]); }
extern "C" void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *h) { processHalf(&dmaBuf[DMA_LEN / 2]); }
extern "C" void DMA2_Stream0_IRQHandler(void) { HAL_DMA_IRQHandler(&hdma_adc1); }

// ------------------------- FFT (radix-2, in place) -------------------------
static void fftInit() {
  for (int i = 0; i < FFT_N; i++) hann[i] = 0.5f - 0.5f * cosf(2.0f * PI * i / (FFT_N - 1));
  for (int i = 0; i < FFT_N / 2; i++) { cosT[i] = cosf(2.0f * PI * i / FFT_N); sinT[i] = -sinf(2.0f * PI * i / FFT_N); }
}

static void fft() {
  for (int i = 1, j = 0; i < FFT_N; i++) {     // bit reversal
    int bit = FFT_N >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { float t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
  }
  for (int len = 2; len <= FFT_N; len <<= 1) {
    int step = FFT_N / len;
    for (int i = 0; i < FFT_N; i += len) {
      for (int k = 0; k < len / 2; k++) {
        float wr = cosT[k * step], wi = sinT[k * step];
        int a = i + k, b = a + len / 2;
        float tr = re[b] * wr - im[b] * wi, ti = re[b] * wi + im[b] * wr;
        re[b] = re[a] - tr; im[b] = im[a] - ti;
        re[a] += tr; im[a] += ti;
      }
    }
  }
}

static float dominantFreq(const int16_t *x) {
  float mean = 0;
  for (int i = 0; i < FFT_N; i++) mean += x[i];
  mean /= FFT_N;
  for (int i = 0; i < FFT_N; i++) { re[i] = (x[i] - mean) * hann[i]; im[i] = 0; }
  fft();
  int kmin = (F_MIN_HZ * FFT_N + FS_CH - 1) / FS_CH, best = kmin;
  float bestMag = -1;
  for (int k = kmin; k <= FFT_N / 2; k++) {
    float m = re[k] * re[k] + im[k] * im[k];
    if (m > bestMag) { bestMag = m; best = k; }
  }
  return (float)best * FS_CH / FFT_N;
}

// ------------------------- Peripheral setup -------------------------
static bool setupAdcDmaTimer() {
  __HAL_RCC_GPIOA_CLK_ENABLE();
  GPIO_InitTypeDef g = {0};
  g.Pin = GPIO_PIN_1 | GPIO_PIN_2 | GPIO_PIN_3 | GPIO_PIN_4;
  g.Mode = GPIO_MODE_ANALOG;
  g.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOA, &g);

  __HAL_RCC_DMA2_CLK_ENABLE();
  hdma_adc1.Instance = DMA2_Stream0;
  hdma_adc1.Init.Channel = DMA_CHANNEL_0;
  hdma_adc1.Init.Direction = DMA_PERIPH_TO_MEMORY;
  hdma_adc1.Init.PeriphInc = DMA_PINC_DISABLE;
  hdma_adc1.Init.MemInc = DMA_MINC_ENABLE;
  hdma_adc1.Init.PeriphDataAlignment = DMA_PDATAALIGN_HALFWORD;
  hdma_adc1.Init.MemDataAlignment = DMA_MDATAALIGN_HALFWORD;
  hdma_adc1.Init.Mode = DMA_CIRCULAR;
  hdma_adc1.Init.Priority = DMA_PRIORITY_HIGH;
  hdma_adc1.Init.FIFOMode = DMA_FIFOMODE_DISABLE;
  if (HAL_DMA_Init(&hdma_adc1) != HAL_OK) return false;

  __HAL_RCC_ADC1_CLK_ENABLE();
  hadc1.Instance = ADC1;
  hadc1.Init.ClockPrescaler = ADC_CLOCK_SYNC_PCLK_DIV4;     // 100 MHz / 4 = 25 MHz
  hadc1.Init.Resolution = ADC_RESOLUTION_12B;
  hadc1.Init.ScanConvMode = ENABLE;
  hadc1.Init.ContinuousConvMode = DISABLE;
  hadc1.Init.DiscontinuousConvMode = DISABLE;
  hadc1.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_RISING;
  hadc1.Init.ExternalTrigConv = ADC_EXTERNALTRIGCONV_T2_TRGO;
  hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc1.Init.NbrOfConversion = N_CH;
  hadc1.Init.DMAContinuousRequests = ENABLE;
  hadc1.Init.EOCSelection = ADC_EOC_SEQ_CONV;
  if (HAL_ADC_Init(&hadc1) != HAL_OK) return false;
  __HAL_LINKDMA(&hadc1, DMA_Handle, hdma_adc1);

  const uint32_t chans[N_CH] = {ADC_CHANNEL_1, ADC_CHANNEL_2, ADC_CHANNEL_3, ADC_CHANNEL_4};  // PA1..PA4
  for (int i = 0; i < N_CH; i++) {
    ADC_ChannelConfTypeDef sc = {0};
    sc.Channel = chans[i];
    sc.Rank = i + 1;
    sc.SamplingTime = ADC_SAMPLETIME_15CYCLES;   // 4 x 27 cycles = 4.3 us < 5 us trigger period
    if (HAL_ADC_ConfigChannel(&hadc1, &sc) != HAL_OK) return false;
  }

  __HAL_RCC_TIM2_CLK_ENABLE();
  uint32_t pclk1 = HAL_RCC_GetPCLK1Freq();
  uint32_t timClk = ((RCC->CFGR & RCC_CFGR_PPRE1) == 0) ? pclk1 : 2 * pclk1;
  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 0;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = timClk / FS_CH - 1;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim2) != HAL_OK) return false;
  TIM_MasterConfigTypeDef m = {0};
  m.MasterOutputTrigger = TIM_TRGO_UPDATE;
  m.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &m) != HAL_OK) return false;

  HAL_NVIC_SetPriority(DMA2_Stream0_IRQn, 1, 0);
  HAL_NVIC_EnableIRQ(DMA2_Stream0_IRQn);

  resetAcc();
  if (HAL_ADC_Start_DMA(&hadc1, (uint32_t *)dmaBuf, DMA_LEN) != HAL_OK) return false;
  if (HAL_TIM_Base_Start(&htim2) != HAL_OK) return false;
  return true;
}

// ------------------------- Float formatting (newlib-nano has no %f) -------------------------
static int appendF(char *buf, int cap, float v, int dec) {
  if (!isfinite(v)) v = 0;
  long scale = 1;
  for (int i = 0; i < dec; i++) scale *= 10;
  bool neg = v < 0;
  double a = fabs((double)v) * scale + 0.5;
  unsigned long long t = (unsigned long long)a;
  unsigned long long ip = t / scale, fp = t % scale;
  int n;
  if (dec > 0) n = snprintf(buf, cap, ",%s%llu.%0*llu", neg ? "-" : "", ip, dec, fp);
  else n = snprintf(buf, cap, ",%s%llu", neg ? "-" : "", ip);
  return n > 0 ? n : 0;
}

// ------------------------- Commands -------------------------
static String cmdA, cmdU;

static void printStatus(Print &out) {
  out.print("# AE status: fs/ch="); out.print(FS_CH);
  out.print(" seq="); out.print(seq);
  out.print(" dropped="); out.print(dropped);
  out.print(" baselines=");
  for (int c = 0; c < N_CH; c++) { out.print(baseline[c]); out.print(c < 3 ? "," : ""); }
  out.print(" thresholds=");
  for (int c = 0; c < N_CH; c++) { out.print(threshold[c]); out.print(c < 3 ? "," : ""); }
  out.println();
}

static void handleCommand(String c, Print &out) {
  c.trim();
  if (c.length() == 0) return;
  if (c == "Z") {
    for (int i = 0; i < N_CH; i++) tareSum[i] = 0;
    tareBlocksLeft = 10;                         // 10 blocks = 1 s
    out.println("# AE tare started (keep pump OFF for 1 s)");
    return;
  }
  if (c == "S") { printStatus(out); return; }
  if (c.charAt(0) == 'T') {
    int p1 = c.indexOf(','), p2 = c.indexOf(',', p1 + 1);
    if (p1 > 0 && p2 > 0) {
      int ch = c.substring(p1 + 1, p2).toInt();
      int val = c.substring(p2 + 1).toInt();
      if (ch >= 1 && ch <= N_CH && val > 0) {
        threshold[ch - 1] = val;
        out.print("# AE threshold ch"); out.print(ch); out.print(" = "); out.println(val);
        return;
      }
    }
  }
  out.println("# AE ? unknown command");
}

static void pollCommands() {
  while (AeSerial.available()) {
    char ch = AeSerial.read();
    if (ch == '\n' || ch == '\r') { handleCommand(cmdA, AeSerial); cmdA = ""; }
    else if (cmdA.length() < 40) cmdA += ch;
  }
#if ECHO_USB
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') { handleCommand(cmdU, Serial); cmdU = ""; }
    else if (cmdU.length() < 40) cmdU += ch;
  }
#endif
}

// ------------------------- Arduino entry points -------------------------
void setup() {
  AeSerial.begin(230400);
#if ECHO_USB
  Serial.begin(115200);
#endif
  pinMode(PC13, OUTPUT);                         // on-board LED (active low)
  fftInit();
  if (!setupAdcDmaTimer()) {
    while (true) {                               // fast blink = setup failed
      digitalWrite(PC13, !digitalRead(PC13));
      AeSerial.println("# AE ERROR: ADC/DMA/TIM setup failed");
      delay(200);
    }
  }
  AeSerial.println("# AE firmware ready");
}

void loop() {
  pollCommands();
  if (!readyFlag) return;

  Acc a[N_CH];
  uint8_t ci;
  uint32_t s;
  noInterrupts();
  for (int c = 0; c < N_CH; c++) a[c] = ready[c];
  ci = readyCap;
  s = seq;
  readyFlag = false;
  interrupts();

  if (tareBlocksLeft > 0) {                      // tare: average raw samples over 10 blocks
    for (int c = 0; c < N_CH; c++) tareSum[c] += (double)a[c].rawsum / BLOCK_FRAMES;
    if (--tareBlocksLeft == 0) {
      for (int c = 0; c < N_CH; c++) baseline[c] = (int16_t)lround(tareSum[c] / 10.0);
      printStatus(AeSerial);
#if ECHO_USB
      printStatus(Serial);
#endif
    }
  }

  char line[600];
  int n = snprintf(line, sizeof(line), "$AE,%lu", (unsigned long)s);
  for (int c = 0; c < N_CH; c++) {
    double N = BLOCK_FRAMES;
    double mean = a[c].sum / N;
    double ms = (double)a[c].sumsq / N;
    float rms = sqrt(ms);
    float sd = sqrt(fmax(0.0, ms - mean * mean));
    float peak = a[c].peak;
    float p2p = (float)a[c].maxv - a[c].minv;
    float energy = (double)a[c].sumsq / FS_CH;
    float crest = peak / (rms + 1e-9f);
    float dur = a[c].dur * 1000.0f / FS_CH;
    float fdom = dominantFreq(cap[ci][c]);
    float vals[9] = {rms, peak, p2p, sd, energy, crest, (float)a[c].hits, dur, fdom};
    const int dec[9] = {2, 0, 0, 2, 2, 2, 0, 3, 0};
    for (int k = 0; k < 9 && n < (int)sizeof(line) - 24; k++) n += appendF(line + n, sizeof(line) - n, vals[k], dec[k]);
  }
  AeSerial.println(line);
#if ECHO_USB
  Serial.println(line);
#endif
  digitalWrite(PC13, (s / 5) % 2);               // slow blink = running
}
