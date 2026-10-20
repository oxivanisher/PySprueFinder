import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.auth import RequiresAuthException
from app.config import settings
from app.database import Base, engine
from app.routers import admin, api, public

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Starting PySprueFinder — git %s", os.getenv("GIT_HASH", "unknown"))

# Ensure directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs("instance", exist_ok=True)

# Create tables
Base.metadata.create_all(bind=engine)

# Inline migration: add columns that may not exist in older DBs
with engine.connect() as _conn:
    for _stmt in [
        "ALTER TABLE sprues ADD COLUMN ocr_profile VARCHAR(50)",
        "ALTER TABLE sprues ADD COLUMN crop_x FLOAT",
        "ALTER TABLE sprues ADD COLUMN crop_y FLOAT",
        "ALTER TABLE sprues ADD COLUMN crop_w FLOAT",
        "ALTER TABLE sprues ADD COLUMN crop_h FLOAT",
    ]:
        try:
            _conn.execute(text(_stmt))
            _conn.commit()
        except Exception:
            pass  # Column already exists

app = FastAPI(title="PySprueFinder")

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# Routers
app.include_router(public.router)
app.include_router(admin.router, prefix="/admin")
app.include_router(api.router, prefix="/api")


# Browsers request /favicon.ico directly, regardless of the <link> tags.
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/static/img/favicon.ico", media_type="image/x-icon")


@app.exception_handler(RequiresAuthException)
async def requires_auth_handler(request: Request, exc: RequiresAuthException):
    return RedirectResponse(url="/login", status_code=302)
