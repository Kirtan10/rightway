"""Export demo artifacts for the frontend / write-up.

Picks the highest-confidence validation up-call (true positive) and writes:
  * ml/demo_upcall.wav          - a copy of that clip
  * ml/demo_spectrogram.png     - its log-mel spectrogram (dark, teal, no axes)
  * ml/demo_spectrogram.json    - the same spectrogram as a 2D array
  * ml/noise_spectrogram.png    - a negative (noise-only) clip's spectrogram

Run:
    python -m ml.export_demo
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

from .features import features_from_path
from .predict import predict
from .train import MAX_CLIPS, SEED, _stratified_split, discover_dataset

ROOT = Path(__file__).resolve().parent
DEMO_WAV = ROOT / "demo_upcall.wav"
DEMO_PNG = ROOT / "demo_spectrogram.png"
DEMO_JSON = ROOT / "demo_spectrogram.json"
NOISE_PNG = ROOT / "noise_spectrogram.png"

TEAL = "teal"  # colormap name used below


def _save_spectrogram_png(spec: np.ndarray, out_path: Path) -> None:
    """Dark-theme, teal colormap, no axes."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    teal_cmap = LinearSegmentedColormap.from_list(
        "teal", ["#001014", "#0a3a44", "#1f8a9c", "#3fe0d0", "#d6fffb"]
    )

    h, w = spec.shape
    fig = plt.figure(figsize=(w / 100.0, h / 100.0), dpi=100)
    fig.patch.set_facecolor("#0b0f14")
    ax = fig.add_axes([0, 0, 1, 1])  # fill the figure, no margins
    ax.set_facecolor("#0b0f14")
    ax.imshow(spec, origin="lower", aspect="auto", cmap=teal_cmap)
    ax.axis("off")
    fig.savefig(out_path, facecolor="#0b0f14", bbox_inches="tight", pad_inches=0)
    plt.close(fig)


def _get_dataset_and_val():
    """Rebuild the exact capped dataset + validation split used in training."""
    ds = discover_dataset()
    if len(ds.samples) > MAX_CLIPS:
        labels_all = np.array([s.label for s in ds.samples])
        keep, _ = _stratified_split(
            labels_all, seed=SEED, frac=MAX_CLIPS / len(labels_all)
        )
        keep = np.sort(keep[:MAX_CLIPS])
        ds.samples = [ds.samples[i] for i in keep]

    labels = np.array([s.label for s in ds.samples])
    _, va = _stratified_split(labels, seed=SEED)
    return ds, va


def main() -> None:
    ds, va = _get_dataset_and_val()

    # Highest-confidence validation up-call (label == 1).
    best_pos = None
    best_conf = -1.0
    first_neg = None
    for i in va:
        s = ds.samples[i]
        if s.label == 1:
            conf = predict(str(s.path))
            if conf > best_conf:
                best_conf, best_pos = conf, s
        elif first_neg is None:
            first_neg = s

    if best_pos is None:
        raise RuntimeError("No positive (up-call) clip found in the validation split.")

    print(f"Best up-call: {best_pos.path.name}  confidence={best_conf:.4f}")

    # 1) Copy the chosen up-call clip.
    shutil.copyfile(best_pos.path, DEMO_WAV)

    # 2) Spectrogram PNG + JSON for the up-call.
    spec = features_from_path(best_pos.path)
    _save_spectrogram_png(spec, DEMO_PNG)
    DEMO_JSON.write_text(
        json.dumps(
            {
                "source": best_pos.path.name,
                "confidence": best_conf,
                "shape": list(spec.shape),
                "spectrogram": spec.tolist(),
            }
        )
    )

    # 3) Noise spectrogram PNG from a negative clip.
    if first_neg is not None:
        noise_spec = features_from_path(first_neg.path)
        _save_spectrogram_png(noise_spec, NOISE_PNG)
        print(f"Noise clip:  {first_neg.path.name}")
    else:
        print("No negative clip found; skipping noise spectrogram.")

    print(f"Wrote:\n  {DEMO_WAV}\n  {DEMO_PNG}\n  {DEMO_JSON}\n  {NOISE_PNG}")


if __name__ == "__main__":
    main()
