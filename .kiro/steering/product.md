# Product

RightWay is a screening aid for protecting North Atlantic right whales from
vessel strikes. It:

- Detects right whale up-calls from hydrophone audio.
- Creates a 10 nautical mile slow zone around a detection.
- Alerts ships operating inside that zone.
- Tracks vessel compliance with the slow zone.
- Writes a human-readable situation brief using Amazon Bedrock.

## Honesty rules (non-negotiable)

These rules exist to keep the product honest about what is real and what is
not. Never blur these lines in UI copy, briefs, docs, demos, or code comments.

- **Vessel data is SIMULATED.** Never present vessel positions, names, speeds,
  or compliance as real AIS or real-world traffic.
- **The classifier is currently trained on SYNTHETIC up-calls.** Real
  Cornell/Kaggle right whale data is the next step, not what ships today. Do
  not imply the model has learned from real recordings.
- **This is a screening aid, not a replacement for official NOAA systems.** It
  assists human judgment; it does not make authoritative determinations.
- **Acknowledge prior art.** Existing WHOI near-real-time buoys and NOAA slow
  zones already do this work. RightWay complements them and does not claim to
  be the first or only solution.
