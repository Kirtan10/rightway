# Requirements — ai-brief

## Introduction

`backend/brief.py` turns a detection + compliance snapshot into a short,
plain-language brief for harbor authorities, using Amazon Bedrock when
available and a hand-written cached brief otherwise. It follows the honesty
rules in `.kiro/steering/product.md`: vessel data is simulated and the demo
clip is synthetic, and these facts must appear in the output.

Scope is limited to three files: `backend/brief.py`,
`backend/cache/brief.json`, and `tests/test_brief.py`. ML-owned files under
`ml/` are read-only here.

## Requirements

### R1 — Call Bedrock via the Converse API

WHEN `generate_brief(detection, compliance)` is called THE SYSTEM SHALL call
Amazon Bedrock via the boto3 `bedrock-runtime` client `converse()`, with
`modelId` taken from the environment variable `BEDROCK_MODEL_ID` and region
from `AWS_REGION` (default `us-east-1`).

### R2 — Brief content and honesty

THE SYSTEM SHALL instruct the model, writing as a harbor authority, to use
ONLY the JSON provided and to write exactly 3 plain-language sentences:
1. what was detected (hydrophone, confidence),
2. how ships responded (before/after speeds, compliance %),
3. a recommended action naming any non-complying vessel.
THE SYSTEM SHALL require the output to state that vessel data is simulated and
the clip is synthetic.

### R3 — Fallback to cache

IF Bedrock fails, OR boto3 is not installed, OR `BEDROCK_MODEL_ID` is unset, OR
the model output is empty, OR the output lacks the word "simulated" THEN THE
SYSTEM SHALL return the cached text from `backend/cache/brief.json`.

### R4 — Public interface

THE SYSTEM SHALL expose `generate_brief_result(...)` returning
`{"brief": str, "source": "bedrock"|"cache"}`, and `generate_brief(...)`
returning only the brief text (the contract function).

### R5 — Demo input never hard-codes confidence

THE SYSTEM SHALL provide `build_demo_input()` returning `(detection,
compliance)` matching the structure.md Demo canon, reading the confidence from
`ml/demo_result.json` and never hard-coding it.

### R6 — Cache-safe __main__

WHEN run as `__main__` THE SYSTEM SHALL call `generate_brief_result` on
`build_demo_input()`, and only when `source == "bedrock"` overwrite
`backend/cache/brief.json`; otherwise it SHALL keep the existing cache. It
SHALL print the result in either case.

### R7 — Bounded Bedrock calls

THE SYSTEM SHALL build the `bedrock-runtime` client with a botocore `Config`
of `connect_timeout=3`, `read_timeout=10`, and `retries={"max_attempts": 1}`,
so a slow or unreachable Bedrock endpoint fails fast and falls back to the cache
(per R3) instead of hanging. The validation checks in `_validation_failure`
are unchanged.
