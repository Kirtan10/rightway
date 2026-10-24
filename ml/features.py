"""Shared audio feature extraction for the up-call classifier.

A single source of truth for the log-mel spectrogram so that training,
inference, and demo export all produce identical features.

Spec:
  sample rate 2000 Hz, n_fft 256, hop 32, 48 mels, fmin 50, fmax 500,
  per-clip normalization, clip padded/trimmed to 2 seconds.
"""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

SAMPLE_RATE = 2000
CLIP_SECONDS = 2.0
CLIP_SAMPLES = round(SAMPLE_RATE * CLIP_SECONDS)

N_FFT = 256
HOP = 32
N_MELS = 48
FMIN = 50
FMAX = 500


def load_audio(path: str | Path, target_sr: int = SAMPLE_RATE) -> np.ndarray:
    """Load a mono waveform at the target sample rate."""
    path = Path(path)
    x, sr = sf.read(path, dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != target_sr and len(x) > 1:
        x = librosa.resample(x, orig_sr=sr, target_sr=target_sr)
    return x.astype(np.float32)


def fix_length(x: np.ndarray, n: int = CLIP_SAMPLES) -> np.ndarray:
    """Pad with zeros or trim to exactly `n` samples."""
    if len(x) == n:
        return x
    if len(x) > n:
        return x[:n]
    out = np.zeros(n, dtype=np.float32)
    out[: len(x)] = x
    return out


def log_mel(x: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Per-clip-normalized log-mel spectrogram, shape (N_MELS, frames)."""
    x = fix_length(x)
    mel = librosa.feature.melspectrogram(
        y=x,
        sr=sr,
        n_fft=N_FFT,
        hop_length=HOP,
        n_mels=N_MELS,
        fmin=FMIN,
        fmax=FMAX,
        power=2.0,
    )
    logmel = librosa.power_to_db(mel, ref=np.max)
    # Per-clip normalization to zero mean / unit std.
    mean = logmel.mean()
    std = logmel.std()
    logmel = (logmel - mean) / (std + 1e-6)
    return logmel.astype(np.float32)


def features_from_path(path: str | Path) -> np.ndarray:
    """Full pipeline: load -> fix length -> log-mel."""
    return log_mel(load_audio(path))
