import logging
import os
import secrets

from dotenv import load_dotenv

load_dotenv()

_PLACEHOLDER_SECRET_KEY = "change-this-to-a-random-secret-key"


def _secret_key() -> str:
    # An unset compose variable (`SECRET_KEY: ${SECRET_KEY}`) arrives as "",
    # which would let anyone sign their own admin session cookie.
    key = os.getenv("SECRET_KEY", "")
    if key and key != _PLACEHOLDER_SECRET_KEY:
        return key
    logging.getLogger(__name__).warning(
        "SECRET_KEY is not set; using a random key (admin sessions reset on restart)"
    )
    return secrets.token_hex(32)


class Settings:
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "changeme")
    SECRET_KEY: str = _secret_key()
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./instance/spruefinder.db")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
    MAX_UPLOAD_PX: int = 4000
    OCR_FONT_SIZE_TOLERANCE: float = float(os.getenv("OCR_FONT_SIZE_TOLERANCE", "0.35"))
    OCR_MIN_SCORE: float = float(os.getenv("OCR_MIN_SCORE", "0.7"))
    GIT_HASH: str = os.getenv("GIT_HASH", "unknown")


settings = Settings()
