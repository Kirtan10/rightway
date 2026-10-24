"""SNR robustness evaluation for the up-call classifier.

Generates FRESH synthetic test clips in memory at a set of FIXED signal-to-noise
ratios (a new random seed, different from training), runs the existing feature +
model.pt pipeline on them (batched), and reports accuracy, AUC and recall at
each SNR. This does NOT retrain and does NOT modify model.pt, metrics.json,
make_synthetic.py, or the training code.

The clip generators are imported from ml.make_synthetic (ocean_noise, ship_tone,
up_call, rms_of) and reused; only the SNR is held fixed here (make_synthetic's
make_clip draws it at random), so the test distribution matches training except
for the controlled SNR.

Run:
    python -m ml.snr_eval
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .features import log_mel
from .make_synthetic import (
    SHIP_FRACTION,
    ocean_noise,
    rms_of,
    ship_tone,
    up_call,
)

ROOT = Path(__file__).resolve().parent
SNR_JSON = ROOT / "snr_eval.json"
SNR_PNG = ROOT / "snr_curve.png"

# New seed, distinct from make_synthetic.SEED (42) and train.SEED (42).
EVAL_SEED = 2024
SNRS_DB = [-20, -16, -12, -8, -4, 0, 4, 8]
N_PER_SNR = 200  # 100 up-call + 100 noise-only
TRAINING_SNR_RANGE_DB = [-8, 10]  # from make_synthetic.make_clip


def _make_clip_fixed_snr(label: int, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Build one test clip, mirroring make_synthetic.make_clip but with a FIXED
    SNR for up-call clips. Noise-only clips are identical to label==0 there.

    Reuses the imported generator functions; the only change from make_clip is
    that snr_db is a parameter instead of rng.uniform(-8, 10).
    """
    noise = ocean_noise(rng)
    noise_level = rng.uniform(0.2, 0.9)
    clip = noise * noise_level

    # Same ship-tone fraction / level as training.
    if rng.random() < SHIP_FRACTION:
        ship = ship_tone(rng)
        ship_level = rng.uniform(0.6, 1.2)
        clip = clip + ship * ship_level

    if label == 1:
        call, call_rms = up_call(rng)
        if call_rms > 1e-9:
            noise_rms = max(rms_of(clip), 1e-9)
            target_call_rms = noise_rms * (10.0 ** (snr_db / 20.0))
            call = call * (target_call_rms / call_rms)
            clip = clip + call

    peak = np.max(np.abs(clip))
    if peak > 0.99:
        clip = clip * (0.99 / peak)
    return clip.astype(np.float32)


def _predict_batch(clips: list[np.ndarray]) -> np.ndarray:
    """Run the existing feature + model.pt pipeline on many clips at once."""
    import torch

    from .predict import _load_model

    model, device = _load_model()
    feats = np.stack([log_mel(c) for c in clips]).astype(np.float32)  # (N, mel, frames)
    x = torch.from_numpy(feats).unsqueeze(1).to(device)  # (N, 1, mel, frames)
    with torch.no_grad():
        probs = torch.sigmoid(model(x)).cpu().numpy().reshape(-1)
    return np.clip(probs, 0.0, 1.0)


def _metrics(probs: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    """Accuracy (@0.5), AUC, and recall (up-calls caught) for one SNR."""
    from sklearn.metrics import roc_auc_score

    preds = (probs >= 0.5).astype(int)
    accuracy = float(np.mean(preds == labels))
    auc = float(roc_auc_score(labels, probs)) if len(np.unique(labels)) > 1 else float("nan")
    pos = labels == 1
    recall = float(np.mean(preds[pos] == 1)) if pos.any() else float("nan")
    return {"accuracy": round(accuracy, 4), "auc": round(auc, 4), "recall": round(recall, 4)}


def evaluate(
    snrs_db: list[int] = SNRS_DB,
    n_per_snr: int = N_PER_SNR,
    seed: int = EVAL_SEED,
) -> dict:
    """Run the SNR sweep and return the results dict (does not write files)."""
    rng = np.random.default_rng(seed)
    half = n_per_snr // 2
    results = []
    for snr in snrs_db:
        labels = np.array([1] * half + [0] * (n_per_snr - half))
        rng.shuffle(labels)
        clips = [_make_clip_fixed_snr(int(y), float(snr), rng) for y in labels]
        probs = _predict_batch(clips)
        row = {"snr_db": int(snr), **_metrics(probs, labels)}
        results.append(row)
        print(f"SNR {snr:+3d} dB  acc={row['accuracy']:.3f}  auc={row['auc']:.3f}  "
              f"recall={row['recall']:.3f}")
    return {
        "data": "synthetic",
        "seed": seed,
        "n_per_snr": n_per_snr,
        "training_snr_range_db": TRAINING_SNR_RANGE_DB,
        "results": results,
    }


def write_curve(report: dict, out_path: Path = SNR_PNG) -> None:
    """Plot accuracy and recall vs SNR on a dark background."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    res = report["results"]
    snrs = [r["snr_db"] for r in res]
    acc = [r["accuracy"] for r in res]
    rec = [r["recall"] for r in res]

    bg = "#0b0f14"
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=120)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)

    lo, hi = report["training_snr_range_db"]
    ax.axvspan(lo, hi, color="#5eead4", alpha=0.12, label="training range")
    ax.axhline(0.5, ls="--", color="#94a3b8", lw=1, label="chance")
    ax.plot(snrs, acc, "-o", color="#5eead4", label="accuracy")
    ax.plot(snrs, rec, "-o", color="#f59e0b", label="recall (up-calls caught)")

    ax.set_xlabel("SNR (dB)")
    ax.set_ylabel("score")
    ax.set_ylim(0.0, 1.02)
    ax.set_title("RightWay classifier vs noise (synthetic test clips)", color="#e5edf7")
    for spine in ax.spines.values():
        spine.set_color("#22304d")
    ax.tick_params(colors="#94a3b8")
    ax.xaxis.label.set_color("#94a3b8")
    ax.yaxis.label.set_color("#94a3b8")
    ax.grid(True, color="#1a2740", lw=0.6)
    leg = ax.legend(facecolor=bg, edgecolor="#22304d", labelcolor="#e5edf7", fontsize=9)
    leg.get_frame().set_alpha(0.9)

    fig.tight_layout()
    fig.savefig(out_path, facecolor=bg)
    plt.close(fig)


def main() -> None:
    report = evaluate()
    SNR_JSON.write_text(json.dumps(report, indent=2) + "\n")
    write_curve(report)
    print(f"Wrote {SNR_JSON}")
    print(f"Wrote {SNR_PNG}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
