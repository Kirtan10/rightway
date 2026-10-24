"""Up-call probability inference.

Contract (see .kiro/steering/structure.md):

    predict(wav_path: str) -> float   # up-call confidence in [0, 1]

Behavior:
  * Lazily loads ml/model.pt on first use.
  * If ml/model.pt is missing or fails to load, raises a clear RuntimeError
    naming the model path.
  * Raises a clear error if the wav file is missing.

Run:
    python -m ml.predict <wav>
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "model.pt"

# Cached (model, device) once loaded.
_MODEL = None
_DEVICE = None


def _pick_device():
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _load_model():
    """Lazy-load the trained CNN. Returns (model, device).

    Raises RuntimeError if the model weights are missing or fail to load.
    """
    global _MODEL, _DEVICE
    if _MODEL is not None:
        return _MODEL, _DEVICE
    if not MODEL_PATH.exists():
        raise RuntimeError(
            f"Trained model weights not found: {MODEL_PATH}. "
            "Train a model first (python -m ml.train)."
        )

    import torch

    from .model import UpCallCNN

    device = _pick_device()
    try:
        ckpt = torch.load(MODEL_PATH, map_location=device)
        n_mels = int(ckpt.get("n_mels", 48))
        model = UpCallCNN(n_mels=n_mels)
        model.load_state_dict(ckpt["state_dict"])
        model.to(device)
        model.eval()
    except Exception as exc:
        raise RuntimeError(f"Failed to load model weights from {MODEL_PATH}: {exc}") from exc
    _MODEL, _DEVICE = model, device
    return _MODEL, _DEVICE


def predict(wav_path: str) -> float:
    """Return up-call probability in [0, 1] for the given WAV file."""
    path = Path(wav_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {wav_path}")

    model, device = _load_model()

    import torch

    from .features import features_from_path

    feat = features_from_path(path)  # (n_mels, frames)
    x = torch.from_numpy(feat).unsqueeze(0).unsqueeze(0).to(device)
    with torch.no_grad():
        prob = torch.sigmoid(model(x)).item()
    return float(min(1.0, max(0.0, prob)))


def main() -> None:
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m ml.predict <wav>", file=sys.stderr)
        raise SystemExit(2)
    print(f"{predict(sys.argv[1]):.4f}")


if __name__ == "__main__":
    main()
