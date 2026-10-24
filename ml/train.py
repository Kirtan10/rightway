"""Train a simple up-call vs. noise classifier.

The data loader auto-detects the dataset layout and uses whichever exists:

1. Kaggle layout (e.g. the Cornell/Marinexplore right-whale up-call challenge):
       <root>/train.csv        with columns (clip_name, label)
       <root>/train/*.aiff     (or .wav) audio clips
   A class-subfolder variant is also accepted:
       <root>/train/0/*.wav, <root>/train/1/*.wav

2. Synthetic layout (produced by ml/make_synthetic.py):
       <root>/data/synthetic/labels.csv   with columns (filename, label)
       <root>/data/synthetic/*.wav

If both exist, the Kaggle layout is preferred (set PREFER=... to override).

This trains a small logistic-regression / MLP model on simple spectral
features. It is intentionally lightweight and dependency-minimal.

Run:
    python ml/train.py
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent
SAMPLE_RATE = 2000
AUDIO_EXTS = (".wav", ".aiff", ".aif", ".flac", ".ogg")

# Which layout to prefer when more than one is present: "kaggle" or "synthetic".
PREFER = "kaggle"


# --- Dataset discovery --------------------------------------------------------

@dataclass
class Sample:
    path: Path
    label: int


@dataclass
class Dataset:
    layout: str          # "kaggle" or "synthetic"
    root: Path
    samples: list[Sample]

    def __len__(self) -> int:
        return len(self.samples)


def _read_label_csv(csv_path: Path, audio_dir: Path) -> list[Sample]:
    """Read a (filename, label) CSV. Column names are detected flexibly."""
    samples: list[Sample] = []
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return samples

    header = [c.strip().lower() for c in rows[0]]
    # Detect filename/label columns from the header, else assume col0/col1.
    fname_idx, label_idx, start = 0, 1, 1
    file_keys = {"filename", "clip_name", "file", "name", "clip"}
    label_keys = {"label", "class", "target", "y"}
    if any(h in file_keys for h in header) or any(h in label_keys for h in header):
        fname_idx = next((i for i, h in enumerate(header) if h in file_keys), 0)
        label_idx = next((i for i, h in enumerate(header) if h in label_keys), 1)
    else:
        # No recognizable header -> treat first row as data.
        start = 0

    for row in rows[start:]:
        if len(row) <= max(fname_idx, label_idx):
            continue
        name = row[fname_idx].strip()
        if not name:
            continue
        # Ensure an extension; Kaggle clip_name sometimes omits it.
        candidate = audio_dir / name
        if not candidate.exists() and Path(name).suffix == "":
            for ext in AUDIO_EXTS:
                if (audio_dir / (name + ext)).exists():
                    candidate = audio_dir / (name + ext)
                    break
        try:
            label = int(float(row[label_idx]))
        except ValueError:
            continue
        samples.append(Sample(path=candidate, label=label))
    return samples


def _find_kaggle(root: Path) -> Dataset | None:
    """Kaggle-style: a train.csv + a train/ dir, or class-subfolders."""
    csv_path = None
    for name in ("train.csv", "labels.csv"):
        if (root / name).exists():
            csv_path = root / name
            break

    train_dir = root / "train"
    if csv_path is not None and train_dir.is_dir():
        samples = _read_label_csv(csv_path, train_dir)
        samples = [s for s in samples if s.path.exists()]
        if samples:
            return Dataset("kaggle", root, samples)

    # Class-subfolder variant: train/0/*, train/1/*
    if train_dir.is_dir():
        samples = []
        for sub in sorted(p for p in train_dir.iterdir() if p.is_dir()):
            if not sub.name.lstrip("-").isdigit():
                continue
            label = int(sub.name)
            for ext in AUDIO_EXTS:
                for p in sub.glob(f"*{ext}"):
                    samples.append(Sample(path=p, label=label))
        if samples:
            return Dataset("kaggle", root, samples)

    return None


def _find_synthetic(root: Path) -> Dataset | None:
    syn_dir = root / "data" / "synthetic"
    csv_path = syn_dir / "labels.csv"
    if csv_path.exists():
        samples = _read_label_csv(csv_path, syn_dir)
        samples = [s for s in samples if s.path.exists()]
        if samples:
            return Dataset("synthetic", syn_dir, samples)
    return None


def discover_dataset(root: Path = ROOT, prefer: str = PREFER) -> Dataset:
    """Return whichever dataset layout exists, honoring `prefer` on ties."""
    # Look both in ml/ and ml/data for a Kaggle drop.
    kaggle = _find_kaggle(root) or _find_kaggle(root / "data")
    synthetic = _find_synthetic(root)

    found = {d.layout: d for d in (kaggle, synthetic) if d is not None}
    if not found:
        raise FileNotFoundError(
            "No dataset found. Expected either a Kaggle layout "
            "(train.csv + train/) or the synthetic layout "
            "(data/synthetic/labels.csv). Run ml/make_synthetic.py to "
            "generate the synthetic set."
        )

    if prefer in found:
        return found[prefer]
    # Otherwise return the only / remaining one.
    return next(iter(found.values()))


# --- Feature extraction -------------------------------------------------------

def load_audio(path: Path, target_sr: int = SAMPLE_RATE) -> np.ndarray:
    x, sr = sf.read(path, dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != target_sr and len(x) > 1:
        # Simple linear resample to the target rate.
        n_out = int(round(len(x) * target_sr / sr))
        x = np.interp(
            np.linspace(0, len(x) - 1, n_out),
            np.arange(len(x)),
            x,
        ).astype(np.float32)
    return x


def extract_features(x: np.ndarray, sr: int = SAMPLE_RATE, n_bands: int = 16) -> np.ndarray:
    """Compact log-mel-ish band-energy features over the up-call band."""
    if len(x) < 2:
        return np.zeros(n_bands + 2, dtype=np.float32)
    x = x - np.mean(x)
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), d=1.0 / sr)

    # Focus on the biologically relevant 20-400 Hz range.
    edges = np.linspace(20.0, 400.0, n_bands + 1)
    bands = np.zeros(n_bands, dtype=np.float32)
    for i in range(n_bands):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if mask.any():
            bands[i] = spec[mask].mean()
    bands = np.log1p(bands)

    rms = float(np.sqrt(np.mean(x ** 2)))
    zcr = float(np.mean(np.abs(np.diff(np.sign(x))) > 0))
    return np.concatenate([bands, [rms, zcr]]).astype(np.float32)


def build_matrix(ds: Dataset) -> tuple[np.ndarray, np.ndarray]:
    feats, labels = [], []
    for s in ds.samples:
        try:
            x = load_audio(s.path)
        except Exception as exc:  # skip unreadable files but keep going
            print(f"  warning: could not read {s.path.name}: {exc}")
            continue
        feats.append(extract_features(x))
        labels.append(s.label)
    return np.asarray(feats, dtype=np.float32), np.asarray(labels, dtype=np.int64)


# --- Model (logistic regression via gradient descent) -------------------------

def train_logreg(X: np.ndarray, y: np.ndarray, epochs: int = 300, lr: float = 0.1):
    mu, sigma = X.mean(0), X.std(0) + 1e-8
    Xn = (X - mu) / sigma
    n, d = Xn.shape
    w = np.zeros(d, dtype=np.float64)
    b = 0.0
    for _ in range(epochs):
        z = Xn @ w + b
        p = 1.0 / (1.0 + np.exp(-z))
        grad_w = Xn.T @ (p - y) / n
        grad_b = float(np.mean(p - y))
        w -= lr * grad_w
        b -= lr * grad_b
    return (w, b, mu, sigma)


def predict(model, X: np.ndarray) -> np.ndarray:
    w, b, mu, sigma = model
    Xn = (X - mu) / sigma
    p = 1.0 / (1.0 + np.exp(-(Xn @ w + b)))
    return p


def main() -> None:
    ds = discover_dataset()
    print(f"Detected '{ds.layout}' layout at: {ds.root}")
    n_pos = sum(1 for s in ds.samples if s.label == 1)
    print(f"  samples: {len(ds)} (label 1: {n_pos}, label 0: {len(ds) - n_pos})")

    print("Extracting features...")
    X, y = build_matrix(ds)
    if len(X) == 0:
        raise RuntimeError("No readable audio samples found.")

    rng = np.random.default_rng(42)
    idx = rng.permutation(len(X))
    split = int(0.8 * len(X))
    tr, te = idx[:split], idx[split:]

    print(f"Training logistic regression on {len(tr)} samples...")
    model = train_logreg(X[tr], y[tr].astype(np.float64))

    p_te = predict(model, X[te])
    pred = (p_te >= 0.5).astype(int)
    acc = float(np.mean(pred == y[te])) if len(te) else float("nan")
    print(f"Held-out accuracy ({len(te)} samples): {acc:.3f}")


if __name__ == "__main__":
    main()
