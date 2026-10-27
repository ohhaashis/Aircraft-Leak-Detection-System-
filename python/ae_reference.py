"""Reference definition of the 9 acoustic-emission (AE) features computed per PZT channel.

The STM32 firmware must compute exactly these, on each 100 ms block of raw ADC samples,
and send them to the ESP32. Use this file to check the firmware: feed the same raw samples
to both and compare. Run  `python ae_reference.py`  for a self-test.

Inputs per channel and block:
  samples   raw 12-bit ADC values (0..4095) for one 100 ms block (fs * 0.1 samples)
  baseline  ADC value with the pump OFF (about 2048 = the 1.65 V bias); measured at tare
  threshold hit threshold in ADC counts above baseline
"""
import numpy as np

FS = 200_000          # samples per second per channel
FFT_N = 1024          # FFT length for dominant frequency
F_MIN = 5_000         # ignore spectrum below this (Hz) when finding the dominant frequency
HIT_DEAD_MS = 1.0     # a new hit can start only after the signal stayed below threshold this long


def ae_features(samples, baseline=2048.0, threshold=150.0, fs=FS):
    x = np.asarray(samples, dtype=float) - baseline      # signal around the tared bias
    xc = x - x.mean()                                    # mean-removed (for std / FFT)
    rms = np.sqrt(np.mean(x ** 2))
    peak = np.max(np.abs(x))
    p2p = x.max() - x.min()
    std = xc.std()
    energy = np.sum(x ** 2) / fs                         # counts^2 * s
    crest = peak / (rms + 1e-9)

    # Hits and duration: a hit starts when |x| crosses the threshold and ends after
    # HIT_DEAD_MS below it. Duration = total time above threshold inside hits (ms).
    above = np.abs(x) > threshold
    dead = int(HIT_DEAD_MS * 1e-3 * fs)
    hits, dur_samples, in_hit, below_count = 0, 0, False, 0
    for a in above:
        if a:
            if not in_hit:
                hits += 1
                in_hit = True
            dur_samples += 1
            below_count = 0
        elif in_hit:
            below_count += 1
            if below_count >= dead:
                in_hit = False
    dur_ms = dur_samples / fs * 1e3

    # Dominant frequency: Hann-windowed FFT of the first FFT_N samples
    seg = x[:FFT_N] - x[:FFT_N].mean()
    seg = seg * np.hanning(len(seg))
    spec = np.abs(np.fft.rfft(seg, n=FFT_N))
    freqs = np.fft.rfftfreq(FFT_N, 1 / fs)
    valid = freqs >= F_MIN
    fdom = freqs[valid][np.argmax(spec[valid])]

    return dict(rms=rms, peak=peak, p2p=p2p, std=std, energy=energy,
                crest=crest, hits=hits, dur=dur_ms, fdom=fdom)


if __name__ == "__main__":
    # Self-test: 40 kHz tone (amplitude 300 counts) + noise + two short bursts
    rng = np.random.default_rng(1)
    n = int(FS * 0.1)
    t = np.arange(n) / FS
    sig = 2048 + 300 * np.sin(2 * np.pi * 40_000 * t) + rng.normal(0, 20, n)
    sig[5000:5100] += 600
    sig[15000:15050] -= 600
    f = ae_features(sig, baseline=2048, threshold=700)
    for k, v in f.items():
        print(f"{k:7s} = {v:,.2f}")
    assert abs(f["fdom"] - 40_000) < FS / FFT_N, "dominant frequency should be ~40 kHz"
    assert f["hits"] == 2, "expected exactly 2 bursts above threshold"
    print("Self-test passed.")
