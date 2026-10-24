# Requirements — classifier

## Introduction

This spec documents the existing ML pipeline in `ml/`: it generates a labeled
synthetic dataset of up-call vs. noise clips, extracts 50–500 Hz log-mel
features, trains a small CNN (with a logistic-regression baseline), persists the
best model and its metrics, and exposes a single inference contract plus demo
assets. The description reflects the code as it stands today.

Honesty note (see `.kiro/steering/product.md`): all training/validation data is
synthetic. Reported metrics are "on synthetic validation data" and are not
real-world detection accuracy.

## Requirements

### R1 — Synthetic up-call and noise generation

WHEN `ml/make_synthetic.py` is run THE SYSTEM SHALL write a balanced set of
2-second, 2000 Hz mono WAV clips to `ml/data/synthetic/`, where label 1 clips
contain a rising frequency-sweep up-call mixed into ocean-like noise (and a
fraction also contain a ship-like tone) and label 0 clips contain noise only,
along with a `labels.csv` (filename,label) and a `README.txt` stating the data
is synthetic.

### R2 — 50–500 Hz log-mel features

THE SYSTEM SHALL provide a single feature function `features_from_path()` in
`ml/features.py` that loads mono audio at 2000 Hz, fixes length to 2 seconds,
and returns a per-clip-normalized log-mel spectrogram computed with
`n_fft=256`, `hop=32`, `n_mels=48`, `fmin=50`, `fmax=500`, used identically by
training, inference, and demo export.

### R3 — CNN training writes model and metrics

WHEN `ml/train.py` is run THE SYSTEM SHALL discover a dataset (preferring a
Kaggle layout if present, else the synthetic layout), train the `UpCallCNN`
over the configured epochs on a stratified split, save the best checkpoint
(by validation AUC) to `ml/model.pt`, and write validation metrics plus a
logistic-regression baseline accuracy to `ml/metrics.json`.

### R4 — Inference contract

THE SYSTEM SHALL expose `predict(wav_path: str) -> float` in `ml/predict.py`
returning an up-call confidence in the range [0, 1] for the given WAV file,
lazily loading `ml/model.pt` on first use.

### R5 — Missing/failed model raises a clear error

IF `ml/model.pt` is missing OR fails to load THEN `predict()` SHALL raise a
`RuntimeError` whose message names the model path. IF the WAV file is missing
THEN `predict()` SHALL raise `FileNotFoundError`.

### R6 — Demo asset export

WHEN `ml/export_demo.py` is run THE SYSTEM SHALL select the highest-confidence
validation up-call and write `ml/demo_upcall.wav`, `ml/demo_spectrogram.png`,
`ml/demo_spectrogram.json`, and a noise-only `ml/noise_spectrogram.png`.

### R7 — Cached demo result

THE SYSTEM SHALL provide a cached demo result at `ml/demo_result.json` holding
the confidence that `predict()` produces for `ml/demo_upcall.wav`, so the rest
of the system can read a canonical demo confidence without re-running the model.

## Non-functional requirements

### NFR1 — Honesty and metrics rules

THE SYSTEM SHALL follow the honesty rules in `.kiro/steering/product.md`:
generated data and the demo clip SHALL be labeled synthetic; metrics from
`ml/metrics.json` SHALL always be described as "on synthetic validation data"
and SHALL never be presented as real-world detection accuracy; confidence
values SHALL come from `ml/predict.py` or `ml/demo_result.json` and never be
hard-coded.
