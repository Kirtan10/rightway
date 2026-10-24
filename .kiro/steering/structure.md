# Structure

## Folder ownership

- **ML teammate:** `ml/` and `backend/brief.py`
- **Sim/app teammate:** `backend/` (everything except `brief.py`) and `frontend/`

Stay within your area of ownership. Coordinate before changing code the other
teammate owns, and treat the contract below as the boundary between them.

## Contract

The two sides integrate only through these interfaces. Keep them stable.

### ML entry point

`ml/predict.py` exposes:

```python
def predict(wav_path: str) -> float:
    """Return up-call confidence in the range 0-1."""
```

### API endpoints

- `POST /detections` returns:

  ```json
  {
    "detection_id": "...",
    "hydrophone_id": "...",
    "confidence": 0.0,
    "zone": { "lat": 0.0, "lon": 0.0, "radius_nm": 10 },
    "vessels_in_zone": []
  }
  ```

- `GET /compliance` returns:

  ```json
  {
    "compliance_pct": 0.0,
    "vessels": [
      { "id": "...", "name": "...", "before": 0.0, "after": 0.0, "status": "..." }
    ]
  }
  ```

- `GET /brief` returns:

  ```json
  { "brief": "..." }
  ```
