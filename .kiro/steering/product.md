# Product

RightWay detects North Atlantic right whale up-calls from hydrophone audio,
creates a 10 nm slow zone, and shows simulated ship responses plus an AI brief
for harbor authorities.

## Honesty rules

- All vessel data is simulated. API responses include `"simulated": true`.
- The classifier is trained on synthetic up-calls, and the demo clip is labeled
  "synthetic demo clip".
- This is a screening aid, not a replacement for official NOAA systems.
- Never claim real-world accuracy.

## Metrics rule

`ml/metrics.json` reports validation on synthetic data only. Whenever metrics
are shown, say "on synthetic validation data". Never present them as detection
accuracy for real whales.

## Required UI and docs copy

- Footer text: "Prototype: classifier trained on synthetic up-calls, not real-world accuracy. All vessel data is simulated. Screening aid, not a replacement for NOAA systems. Map is schematic."
- Never say the classifier was trained on real or public recordings. Never say
  vessel tracks come from AIS.
- Every count or statistic in the UI comes from the simulation and resets to 0
  on `/reset`. No hard-coded history numbers.
- Confidence scores always come from `ml/predict.py` or `ml/demo_result.json`.
  Never hard-code a confidence value.
- The spectrogram panel shows "synthetic demo clip" while the demo call plays.
- The brief panel label is "AI BRIEF · BEDROCK" when source is "bedrock",
  otherwise "AI BRIEF · CACHED".
