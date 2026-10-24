# Tasks — frontend-map

- [ ] 1. `frontend/index.html`: header (title, tagline, pill, DEMO DATA badge,
      tabs), two-column Live bay layout (map + 5 cards), Ship compliance tab,
      exact footer copy. Pinned Leaflet 1.9.4 CSS/JS from unpkg.
      _R1, R2, R5, R6, R7_

- [ ] 2. `frontend/style.css`: dark navy theme, teal accent `#5eead4`,
      desktop-first two-column grid, cards, status chips, legend, tabs,
      pixelated spectrogram image.
      _R2, R3, R5_

- [ ] 3. `frontend/app.js`: API constant; map + CARTO tiles; vessel markers with
      per-id tooltip direction/offset; H-2 marker from the zone only; Simulate
      demo flow (detection, dashed zone, spectrogram swap, audio, confidence,
      1 s polling for 10 s, button disable); Reset; cards; compliance tab;
      error handling; `textContent` escaping.
      _R1, R3, R4, R5, R7, R8, R9_

- [ ] 4. Manual verification checklist with the backend running on :8000.
      _R1–R9_

- [x] 5. Keep Simulate disabled from detection start until Reset (not just the
      10 s polling window); on a 409 from `/detections`, show its detail in the
      spectrogram card and keep Simulate disabled. Hide the "Stellwagen Bank
      sanctuary" label while zoomed into the zone and show it again after Reset.
      _R8, R9, R10_
