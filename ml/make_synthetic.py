"""Generate a labeled SYNTHETIC dataset of marine-mammal-style audio clips.

Each clip is a 2-second, 2000 Hz mono WAV file. Half the clips contain a
synthetic "up-call" (a rising frequency sweep) mixed into ocean-like noise;
the other half contain noise only. A labels.csv maps each filename to its
label (1 = up-call present, 0 = noise only).

IMPORTANT: this data is entirely SYNTHETIC. It is not derived from any real
hydrophone recordings and must not be presented as such.

Run:
    python ml/make_synthetic.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

# --- Configuration -----------------------------------------------------------

SEED = 42
SAMPLE_RATE = 2000            # Hz
CLIP_SECONDS = 2.0
N_SAMPLES = int(round(SAMPLE_RATE * CLIP_SECONDS))
N_CLIPS = 4000               # total clips; 50/50 split between labels
SHIP_FRACTION = 0.40         # fraction of clips that also get a ship-like tone

OUT_DIR = Path(__file__).resolve().parent / "data" / "synthetic"


# --- Signal helpers -----------------------------------------------------------

def _bandpass(x: np.ndarray, low: float, high: float, order: int = 4) -> np.ndarray:
    """Zero-to-Nyquist safe Butterworth bandpass."""
    nyq = SAMPLE_RATE / 2.0
    low_n = max(low / nyq, 1e-4)
    high_n = min(high / nyq, 0.999)
    sos = butter(order, [low_n, high_n], btype="band", output="sos")
    return sosfilt(sos, x)


def pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    """Approximate pink (1/f) noise via FFT shaping of white noise."""
    white = rng.standard_normal(n)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, d=1.0 / SAMPLE_RATE)
    # 1/f amplitude shaping (pink). Avoid div-by-zero at DC.
    scale = np.ones_like(freqs)
    scale[1:] = 1.0 / np.sqrt(freqs[1:])
    spectrum *= scale
    out = np.fft.irfft(spectrum, n=n)
    return out


def brown_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    """Brown (1/f^2) noise as the cumulative sum of white noise."""
    white = rng.standard_normal(n)
    out = np.cumsum(white)
    out -= out.mean()
    return out


def normalize(x: np.ndarray) -> np.ndarray:
    peak = np.max(np.abs(x))
    if peak < 1e-12:
        return x
    return x / peak


def ocean_noise(rng: np.random.Generator) -> np.ndarray:
    """Low-frequency ocean-like ambient noise, bandpassed 20-800 Hz."""
    # Mix pink and brown noise for a low-frequency-heavy spectrum.
    mix = pink_noise(N_SAMPLES, rng) + 0.7 * brown_noise(N_SAMPLES, rng)
    mix = _bandpass(mix, 20.0, 800.0)
    return normalize(mix)


def ship_tone(rng: np.random.Generator) -> np.ndarray:
    """A loud, slowly passing ship-like hum: 60-120 Hz fundamental + harmonics.

    Amplitude follows a slow pass-by envelope (rises then falls) to emulate a
    vessel moving past the sensor.
    """
    t = np.arange(N_SAMPLES) / SAMPLE_RATE
    f0 = rng.uniform(60.0, 120.0)
    # Slight slow frequency drift as the ship passes (Doppler-ish).
    drift = rng.uniform(-4.0, 4.0)
    inst_f = f0 + drift * (t / CLIP_SECONDS)
    phase = 2.0 * np.pi * np.cumsum(inst_f) / SAMPLE_RATE

    sig = np.sin(phase)
    # Harmonics with decaying amplitude.
    for h, amp in [(2, 0.5), (3, 0.3), (4, 0.15), (5, 0.08)]:
        sig += amp * np.sin(h * phase + rng.uniform(0, 2 * np.pi))

    # Slow pass-by envelope: Gaussian bump centered at a random time.
    center = rng.uniform(0.3, 0.7) * CLIP_SECONDS
    width = rng.uniform(0.6, 1.2)
    env = np.exp(-0.5 * ((t - center) / width) ** 2)
    sig = sig * env
    return normalize(sig)


def up_call(rng: np.random.Generator) -> tuple[np.ndarray, float]:
    """A rising frequency sweep (an up-call) placed at a random time.

    Returns the full-length (N_SAMPLES) signal and its RMS over the active
    region (used later for SNR scaling).
    """
    dur = rng.uniform(0.8, 1.2)
    n_call = int(round(dur * SAMPLE_RATE))
    n_call = min(n_call, N_SAMPLES)
    tc = np.arange(n_call) / SAMPLE_RATE

    f_start = rng.uniform(50.0, 90.0)
    f_end = rng.uniform(150.0, 250.0)
    # Linear sweep. Instantaneous frequency goes f_start -> f_end.
    k = (f_end - f_start) / (n_call / SAMPLE_RATE)
    inst_f = f_start + k * tc
    phase = 2.0 * np.pi * (f_start * tc + 0.5 * k * tc ** 2)

    call = np.sin(phase)
    # Slight random harmonic content.
    for h, base_amp in [(2, 0.3), (3, 0.12)]:
        call += rng.uniform(0.5, 1.0) * base_amp * np.sin(h * phase)

    # Smooth amplitude envelope (Hann-like raised cosine) over the call.
    env = np.sin(np.pi * np.arange(n_call) / max(n_call - 1, 1)) ** 2
    call = call * env

    # Place at a random offset inside the clip.
    out = np.zeros(N_SAMPLES)
    max_start = N_SAMPLES - n_call
    start = rng.integers(0, max_start + 1) if max_start > 0 else 0
    out[start:start + n_call] = call

    active = out[start:start + n_call]
    rms = np.sqrt(np.mean(active ** 2)) if active.size else 0.0
    return out, rms


def rms_of(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0


# --- Clip assembly ------------------------------------------------------------

def make_clip(label: int, rng: np.random.Generator) -> np.ndarray:
    # Base ocean noise with a random level per clip.
    noise = ocean_noise(rng)
    noise_level = rng.uniform(0.2, 0.9)
    clip = noise * noise_level

    # Random 40% of clips get a loud ship-like tone.
    if rng.random() < SHIP_FRACTION:
        ship = ship_tone(rng)
        ship_level = rng.uniform(0.6, 1.2)  # "loud"
        clip = clip + ship * ship_level

    if label == 1:
        call, call_rms = up_call(rng)
        if call_rms > 1e-9:
            # Mix at a target SNR (dB) relative to the current clip RMS.
            snr_db = rng.uniform(-8.0, 10.0)
            noise_rms = rms_of(clip)
            if noise_rms < 1e-9:
                noise_rms = 1e-9
            target_call_rms = noise_rms * (10.0 ** (snr_db / 20.0))
            call = call * (target_call_rms / call_rms)
            clip = clip + call

    # Prevent hard clipping while keeping a healthy level.
    peak = np.max(np.abs(clip))
    if peak > 0.99:
        clip = clip * (0.99 / peak)
    return clip.astype(np.float32)


def main() -> None:
    rng = np.random.default_rng(SEED)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Build a balanced, shuffled label list.
    half = N_CLIPS // 2
    labels = np.array([1] * half + [0] * (N_CLIPS - half))
    rng.shuffle(labels)

    rows = []
    counts = {0: 0, 1: 0}
    for i, label in enumerate(labels):
        label = int(label)
        clip = make_clip(label, rng)
        fname = f"clip_{i:05d}.wav"
        sf.write(OUT_DIR / fname, clip, SAMPLE_RATE, subtype="PCM_16")
        rows.append((fname, label))
        counts[label] += 1

    # Write labels.csv
    with open(OUT_DIR / "labels.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "label"])
        writer.writerows(rows)

    # Write the SYNTHETIC-data notice.
    (OUT_DIR / "README.txt").write_text(
        "SYNTHETIC data, not real recordings.\n\n"
        "Every WAV file in this directory was generated procedurally by\n"
        "ml/make_synthetic.py. These clips are NOT derived from any real\n"
        "hydrophone or field recordings and must not be presented as such.\n\n"
        f"Format: {CLIP_SECONDS:.0f}-second mono WAV, {SAMPLE_RATE} Hz, 16-bit PCM.\n"
        "Labels (labels.csv): 1 = synthetic up-call present, 0 = noise only.\n"
    )

    print(f"Wrote {len(rows)} clips to {OUT_DIR}")
    print(f"  label 1 (up-call):   {counts[1]}")
    print(f"  label 0 (noise only):{counts[0]}")
    print(f"  labels.csv:          {OUT_DIR / 'labels.csv'}")
    print(f"  README.txt:          {OUT_DIR / 'README.txt'}")


if __name__ == "__main__":
    main()
