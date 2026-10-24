# Design — classifier

## Data flow

```
make_synthetic.py        features.py            model.py / train.py
  ocean + ship noise   ->  load_audio ->        UpCallCNN (3 conv blocks ->
  + up-call sweeps         fix_length (2 s)     global avg pool -> 1 logit)
  -> data/synthetic/*.wav  log-mel 50-500 Hz        |
  + labels.csv             (48 mels)                v
                                            train.py -> ml/model.pt
                                                     -> ml/metrics.json
                                                        |
                                                        v
  predict(wav_path) --(features_from_path)--> UpCallCNN -> sigmoid -> float in [0,1]
                                                        |
                           export_demo.py --------------+--> demo_upcall.wav,
                                                             demo_spectrogram.{png,json}
                           cache_demo.py (planned) ---------> demo_result.json
```

The feature extractor in `features.py` is the single source of truth, imported
by both `train.py` (`_build_spectrograms`) and `predict.py`, so training and
inference see identical inputs. `export_demo.py` rebuilds the exact capped
dataset and stratified validation split from `train.py` and runs `predict()` to
pick the best true-positive clip.

### Components

- `make_synthetic.py` — procedural generator. Pink+brown ocean noise
  (bandpassed 20–800 Hz), optional ship tone (60–120 Hz fundamental + harmonics
  with a pass-by envelope), and up-call sweeps (f_start 50–90 Hz -> f_end
  150–250 Hz) mixed at a random SNR (−8 to +10 dB). Balanced 50/50, seed 42.
- `features.py` — `load_audio` -> `fix_length` -> `log_mel` (per-clip zero
  mean / unit std).
- `model.py` — `UpCallCNN`: three Conv-BN-ReLU-MaxPool blocks (1→16→32→64),
  adaptive global average pool, single linear logit. Deliberately small so it
  trains in a few epochs on CPU/MPS.
- `train.py` — dataset discovery (Kaggle layout preferred, synthetic fallback),
  stratified split, Adam + BCEWithLogits for 6 epochs, best-by-AUC checkpoint,
  plus a from-scratch logistic-regression baseline on compact band-energy
  features for comparison.
- `predict.py` — lazy model load, `features_from_path`, sigmoid, clamp to
  [0, 1]. Raises `RuntimeError` naming the path if the model is missing/broken.
- `export_demo.py` — demo spectrogram/audio assets.

## Why the data is synthetic

The intended real dataset was the Cornell/Marinexplore right-whale up-call
Kaggle challenge. The download was blocked: the competition rules page returned
HTTP 403, so the data could not be accepted/downloaded. `train.py` keeps full
support for the Kaggle layout (`train.csv` + `train/`, or class subfolders) and
prefers it when present, but with no access the pipeline runs end to end on the
procedurally generated synthetic set instead. The synthetic generator is
designed to exercise the same 50–500 Hz up-call band, ship interference, and
SNR variation the real task involves.

## Metrics — on synthetic validation data

From `ml/metrics.json` (6 epochs, 4000 synthetic clips, seed 42). These are
**synthetic** results, not real-world detection accuracy.

| Model                        | Metric            | Value  |
| ---------------------------- | ----------------- | ------ |
| UpCallCNN                    | best val accuracy | 0.9975 |
| UpCallCNN                    | best val AUC      | 1.0    |
| Logistic-regression baseline | val accuracy      | 0.9675 |

Per-epoch CNN validation AUC climbs from ~0.998 (epoch 1) to 1.0 by epochs 5–6;
validation accuracy tracks between ~0.69 (epoch 1) and ~0.999.

## Limitations

The near-perfect synthetic scores (AUC 1.0, demo clip confidence ≈ 1.00)
demonstrate that the pipeline works **end to end** — generation, features,
training, checkpointing, and inference all connect correctly — not that the
model would perform this well on real audio. Synthetic up-calls are cleanly
separable from the generated noise and ship tones; real up-calls overlap with
ambient noise and vessel tones far more, and real recordings carry
distribution shift the synthetic set does not capture. Treat the numbers as a
functional smoke test of the pipeline, consistent with the screening-aid framing
in `product.md`.
