# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

Full-stack web app for finding Warhammer miniature parts on sprues by photo.
Stack: FastAPI · SQLite/SQLAlchemy · Jinja2 · Tailwind CDN · Vanilla JS · RapidOCR (ONNX Runtime) · OpenCV · Docker

## Environment

- Python 3.12 with a virtual environment at `.venv/`
- Black code formatter is configured in the PyCharm project (`.idea/misc.xml`)

## Running the project

```bash
# Dev (with hot reload)
python run.py

# Or directly
.venv/bin/uvicorn app.main:app --reload

# Docker
docker compose up --build
```

## Setup notes

Dependencies are in `requirements.txt`. Install with:
```bash
pip install -r requirements.txt
```

No system OCR packages are needed: `rapidocr_onnxruntime` ships its models inside the wheel. It
depends on `opencv-python` (not `-headless`) — never install both, they share the `cv2` module.

Copy `.env.example` to `.env` and set `ADMIN_PASSWORD` and `SECRET_KEY`.

## Key structure

```
app/
  main.py          — FastAPI app factory; logs git hash at startup via GIT_HASH env var
  config.py        — Settings from env
  database.py      — SQLAlchemy engine + get_db
  models.py        — Project, Sprue, NumberLocation
  schemas.py       — Pydantic schemas
  auth.py          — Session-based admin auth
  ocr.py           — Sprue-number OCR pipeline (see below)
  routers/
    public.py      — Public web routes
    admin.py       — Admin web routes (/admin/*)
    api.py         — JSON API (/api/*)
  static/          — CSS + JS
  templates/       — Jinja2 HTML
instance/          — SQLite DB (gitignored)
uploads/           — Uploaded images (gitignored)
```

## OCR Pipeline (`app/ocr.py`)

RapidOCR (PaddleOCR PP-OCRv4 detector + recogniser on ONNX Runtime). Tesseract was replaced
because its document layout analysis returns mostly noise on sparse labels in a cluttered photo.

`process_image(path, profile="auto")` returns `(list[dict], profile)`. Only `auto` exists; the
`profile` API param and `sprues.ocr_profile` column are kept for compatibility (old rows may still
hold legacy Tesseract profile names like `clear`/`bw`).

1. **Coarse pass** at native resolution — finds bold, plated labels and measures label height.
2. **Fine pass** upscaled so labels reach ~100 px (`_TARGET_LABEL_PX`, scale clamped 1–4×) — finds
   the thin, low-contrast numbers moulded straight into the frame. Upscale is the dominant accuracy
   knob; detector thresholds and CLAHE-style preprocessing made no measurable difference.
3. Union → one detection per location (highest score wins) → `OCR_MIN_SCORE` (env, default 0.7) →
   font-size filter keeping the densest height cluster ±`OCR_FONT_SIZE_TOLERANCE` (env, default 0.35).

Key implementation details:
- Both passes are tiled (2400 px detector tiles, 320 px overlap; boxes touching an inner tile edge
  are dropped) to bound memory: ~1.3 GB peak, vs ~7 GB for an untiled 2× pass on a 4000 px photo
- RapidOCR's own resizing is disabled (`max_side_len`, `det_limit_*`) — its defaults shrink photos
  until the digits vanish
- Engine is a lazy singleton guarded by a lock (RapidOCR mutates per-call state)
- Text parsed as 1–3 digits after stripping edge punctuation (`"79-"` → 79); range 1–999
- Returns relative coords (0.0–1.0) + `confidence` 0–100; frontend highlight boxes use CSS `%`
- `get_debug_preview(path)` re-runs OCR and returns a JPEG with accepted (green) / rejected (red) candidates
- Benchmark, 3 full-sprue phone photos / 108 labels: ~95% recall, 0–1 false positives, 10–20 s/image
  on a 24-core desktop. Remaining misses: rotated single digits, labels half-hidden by the frame edge
- Sprues table has `ocr_profile VARCHAR(50)` column added via inline migration in `main.py`

## Deployment & CI/CD

**GitLab CI** (`.gitlab-ci.yml`) — three stages on every push, release+deploy on `main` only:
1. `build` — `docker build --build-arg GIT_HASH=$CI_COMMIT_SHORT_SHA` + push as `spruefinder:$CI_COMMIT_REF_NAME`
2. `release` — retag as `spruefinder:latest` and push
3. `deploy` — POST to `$PORTAINER_WEBHOOK_URL` (CI env var) to trigger Portainer redeploy

**Registry:** `registry.example.com/example/pyspruefinder/spruefinder`

**Production** (`docker-compose.yml`): pulls from registry, bind address controlled by `SERVICE_IP` env var (default `0.0.0.0`), port 8000, volumes at `/srv/spruefinder/`. Env vars use `${VAR:-default}` syntax.

**Local build test** (`docker-compose.build.yml`): builds from source, binds `0.0.0.0:8000`.

## Important Notes

- `sprue_edit.html` receives `locations_json` (list of dicts) from the admin router — NOT raw SQLAlchemy objects
- `tojson` Jinja2 filter requires dicts/lists; serialize SQLAlchemy objects first via `NumberLocationOut.model_validate`
