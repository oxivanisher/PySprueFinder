import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "changeme")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-to-a-random-secret-key")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./instance/spruefinder.db")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
    MAX_UPLOAD_PX: int = 4000
    MAX_OCR_PX: int = 2000
    OCR_FONT_SIZE_TOLERANCE: float = float(os.getenv("OCR_FONT_SIZE_TOLERANCE", "0.10"))
    OCR_UPSCALE: float = float(os.getenv("OCR_UPSCALE", "1.0"))


settings = Settings()
