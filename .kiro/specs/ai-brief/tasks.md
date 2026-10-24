# Tasks — ai-brief

- [ ] 1. Write `backend/cache/brief.json` (remove `backend/cache/.gitkeep`) with
      `"source": "cache"` and the hand-written fallback brief, filling in
      `confidence_display` from the ML demo result.
      _R3, R4_

- [ ] 2. Implement `backend/brief.py`: `_get_client()`, prompt builders, Bedrock
      `converse()` call, `generate_brief_result()`, `generate_brief()`,
      cache read/write, `build_demo_input()`, and a cache-safe `__main__`.
      _R1, R2, R3, R4, R5, R6_

- [ ] 3. Add `tests/test_brief.py` with 5 tests: Bedrock raising -> cache text
      with source "cache"; output missing "simulated" -> cache; valid fake
      output -> source "bedrock"; cached brief contains both "simulated" and
      "synthetic"; `build_demo_input()` confidence equals `ml/demo_result.json`.
      Add no conftest unless imports fail.
      _R3, R4, R5_

- [ ] 4. Add `boto3` to `requirements.txt` if missing (shared file; heads-up to
      teammate given).
      _R1_

- [ ] 5. Run `ruff check backend/brief.py tests/` and
      `pytest -q tests/test_brief.py`.
      _R1–R6_

- [x] 6. Bound Bedrock calls: `_get_client()` builds the `bedrock-runtime`
      client with a botocore `Config(connect_timeout=3, read_timeout=10,
      retries={"max_attempts": 1})` so a slow/unreachable endpoint fails fast
      and falls back to the cache. Validation checks unchanged.
      _R7_