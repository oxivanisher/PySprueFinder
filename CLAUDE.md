# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

Full-stack web app for finding Warhammer miniature parts on sprues by photo.
Stack: FastAPI · SQLite/SQLAlchemy · Jinja2 · Tailwind CDN · Vanilla JS · Tesseract OCR · OpenCV · Docker

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

Tesseract OCR must be installed on the host for non-Docker dev:
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-eng
```

Copy `.env.example` to `.env` and set `ADMIN_PASSWORD` and `SECRET_KEY`.

## Key structure

```
app/
  main.py          — FastAPI app factory
  config.py        — Settings from env
  database.py      — SQLAlchemy engine + get_db
  models.py        — Project, Sprue, NumberLocation
  schemas.py       — Pydantic schemas
  auth.py          — Session-based admin auth
  ocr.py           — Multi-profile OCR pipeline (see below)
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

Multi-profile system — `process_image(path, profile)` returns `(list[dict], effective_profile)`.

| Profile | Strategy |
|---------|----------|
| `auto` | Runs all candidates, merges with font-size filter, returns best |
| `clear` | CLAHE + adaptive threshold, 2 block sizes, both polarities (4 passes) |
| `retinex` | Illumination normalisation at σ=30 and σ=60, both polarities (4 passes) |
| `embossed` | 6-dir emboss, top-hat, black-hat, Sobel (5 passes) |
| `bw` | Threshold sweep across 7 levels (110–218), both polarities (14 passes) |
| `raw` | No preprocessing, single Tesseract pass |

Key implementation details:
- Every Tesseract call upscales the image 2× first (`_OCR_UPSCALE = 2.0`) — critical for small sprue numbers
- Digit whitelist only (`0123456789`), valid range 1–999, confidence threshold ≥ 15
- Deduplication via IoU > 0.3 merge; font-size filter keeps detections within ±20% of median height
- Returns relative coords (0.0–1.0); frontend highlight boxes use CSS `%` positioning
- `get_debug_preview(path, profile)` returns a JPEG grid of preprocessed images (no OCR re-run)
- Sprues table has `ocr_profile VARCHAR(50)` column added via inline migration in `main.py`

## Deployment & CI/CD

**GitLab CI** (`.gitlab-ci.yml`) — three stages on every push, release+deploy on `main` only:
1. `build` — `docker build` + push to GitLab registry as `spruefinder:$CI_COMMIT_REF_NAME`
2. `release` — retag as `spruefinder:latest` and push
3. `deploy` — POST to `$PORTAINER_WEBHOOK_URL` (CI env var) to trigger Portainer redeploy

**Registry:** `gitlab.example.com:5050/example/pyspruefinder/spruefinder`

**Production** (`docker-compose.yml`): pulls from registry, binds `0.0.0.0:8000`, volumes at `/srv/spruefinder/`.

**Local build test** (`docker-compose.build.yml`): builds from source, binds `0.0.0.0:8000`.

## Important Notes

- `sprue_edit.html` receives `locations_json` (list of dicts) from the admin router — NOT raw SQLAlchemy objects
- `tojson` Jinja2 filter requires dicts/lists; serialize SQLAlchemy objects first via `NumberLocationOut.model_validate`
