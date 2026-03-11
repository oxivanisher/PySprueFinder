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
  ocr.py           — Two-pass OCR pipeline
  routers/
    public.py      — Public web routes
    admin.py       — Admin web routes (/admin/*)
    api.py         — JSON API (/api/*)
  static/          — CSS + JS
  templates/       — Jinja2 HTML
instance/          — SQLite DB (gitignored)
uploads/           — Uploaded images (gitignored)
```
