# Tasks — classifier

## Completed

- [x] 1. Synthetic dataset generator (`ml/make_synthetic.py`): balanced up-call
      vs. noise clips with ocean noise, ship tones, SNR scaling, `labels.csv`,
      and a synthetic-data `README.txt`.
      _R1_
- [x] 2. Shared log-mel feature extractor (`ml/features.py`), 50–500 Hz, 48
      mels, used by training, inference, and demo export.
      _R2_
- [x] 3. `UpCallCNN` model (`ml/model.py`): 3 conv blocks + global pool + linear
      head.
      _R3_
- [x] 4. Training pipeline (`ml/train.py`): dataset discovery (Kaggle preferred,
      synthetic fallback), stratified split, CNN training, logistic-regression
      baseline; writes `ml/model.pt` and `ml/metrics.json`.
      _R3_
- [x] 5. Inference contract `predict(wav_path: str) -> float` in
      `ml/predict.py`, lazy model load, clamp to [0, 1].
      _R4_
- [x] 6. Removed the 0.93 stand-in fallback from `predict()`; it now raises
      `RuntimeError` naming the path when the model is missing or fails to load
      (with test `test_missing_model_raises_runtime_error_naming_path`).
      _R5_
- [x] 7. Demo asset export (`ml/export_demo.py`): best up-call WAV + spectrogram
      PNG/JSON and a noise spectrogram.
      _R6_
- [x] 8. Pinned lint rules in `ruff.toml`; `ml/` passes ruff.
      _NFR1_

## Planned

- [x] 9. Add `ml/cache_demo.py` that runs `predict()` on `ml/demo_upcall.wav`
      and writes `ml/demo_result.json` as
      `{"confidence": <float rounded to 4 places>, "confidence_display":
      "<2 decimals>", "clip": "ml/demo_upcall.wav", "synthetic_demo_clip":
      true}`. Runnable as `python -m ml.cache_demo`.
      _R7_

- [x] 10. Add `ml/tests/test_cache_demo.py`: running it writes valid JSON with
      those keys, the confidence matches `predict()` on the same file, and
      `confidence_display` is a 2-decimal string (not a percentage). Write to a
      tmp path in the test so the real file isn't overwritten.
      _R7_

- [x] 11. Add `ml/snr_eval.py` (runnable as `python -m ml.snr_eval`): an SNR
      robustness evaluation. Reuse the `make_synthetic.py` generator functions
      (imported, not copied) to build fresh in-memory test clips with a NEW
      seed; for each fixed SNR in [-20,-16,-12,-8,-4,0,4,8] dB make 200 clips
      (100 up-call / 100 noise, ship tones at the training fraction) and run the
      existing feature + `model.pt` pipeline (batched). Compute accuracy
      (threshold 0.5), AUC and recall per SNR; write `ml/snr_eval.json` and
      `ml/snr_curve.png`. Does not retrain or touch `model.pt`/`metrics.json`/
      `make_synthetic.py`/training code.
      _NFR1_

- [x] 12. Add `ml/tests/test_snr_eval.py`: a tiny run (2 SNRs, 10 clips each)
      writes JSON with the expected keys and values in [0, 1], to a tmp path.
      _NFR1_
