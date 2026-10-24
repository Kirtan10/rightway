# Design — ai-brief

## Overview

`backend/brief.py` is a small, dependency-light module. Bedrock access is
optional and always has a safe fallback to the cached brief, so the function is
runnable with no AWS setup and in tests.

## Components

### `_get_client()`
Lazily imports `boto3` inside the function so tests can monkeypatch it and so a
missing boto3 is a handled fallback, not an import error. Builds a
`bedrock-runtime` client using `AWS_REGION` (default `us-east-1`). Raises if
boto3 is missing or `BEDROCK_MODEL_ID` is unset (caller treats this as a
fallback trigger).

### Prompt building
- `_system_prompt()` — fixed system text: write as a harbor authority, use ONLY
  the provided JSON, exactly 3 sentences (detection / response / recommended
  action naming any non-complying vessel), and state that vessel data is
  simulated and the clip is synthetic.
- `_user_message(detection, compliance)` — serializes the two dicts as JSON for
  the user turn.

### Bedrock call
`converse()` is called with:
- `modelId=BEDROCK_MODEL_ID`
- `system=[{"text": _system_prompt()}]`
- `messages=[{"role": "user", "content": [{"text": _user_message(...)}]}]`
- `inferenceConfig={"maxTokens": 300, "temperature": 0.2}`
The text is read from `response["output"]["message"]["content"][0]["text"]`.

### `generate_brief_result(detection, compliance) -> dict`
Tries Bedrock. Returns `{"brief", "source": "bedrock"}` only if the output is
non-empty and contains the word "simulated". On any failure, or if that check
fails, returns `{"brief": <cache text>, "source": "cache"}`.

### `generate_brief(detection, compliance) -> str`
Contract function: returns `generate_brief_result(...)["brief"]`.

### Cache helpers
- `_read_cache()` reads `backend/cache/brief.json` and returns its `brief`.
- `_write_cache(result)` writes `{"brief","source"}`.

### `build_demo_input() -> (detection, compliance)`
Matches the structure.md Demo canon: detection at H-2, 10 nm zone, 4 vessels in
zone (Nordic Tide 16->10, Harbor Queen 22->10, Blue Fin II 11->9, Cape Runner
19->17 not_complying), compliance 75%. It reads both `confidence` and the
2-decimal `confidence_display` (e.g. "1.00", never a percentage) from
`ml/demo_result.json`; neither value is hard-coded in source. If that ML-owned
file is absent, `build_demo_input()` raises a clear `FileNotFoundError` naming
the path and telling the user to run `python -m ml.cache_demo` — there is no
spectrogram fallback.

## Error handling

All Bedrock/boto3 errors are caught broadly and funneled to the cache fallback;
the blind catch carries a `# noqa: BLE001` with a reason, matching repo
conventions. The cache read is the last line of defense and is always present.

## Testing

`tests/test_brief.py` monkeypatches `_get_client` / the client's `converse` to
simulate failures and fake outputs. Five tests cover: Bedrock raising -> cache;
output missing "simulated" -> cache; valid fake output -> bedrock; cached brief
contains "simulated" and "synthetic"; `build_demo_input()` confidence equals the
ML demo result. `backend/__init__.py` exists, so no conftest is added unless
imports fail.
