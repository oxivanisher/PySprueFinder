import hmac
import logging
import os

from fastapi import Request
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings

logger = logging.getLogger(__name__)


class RequiresAuthException(Exception):
    pass


def require_admin(request: Request):
    if not request.session.get("is_admin"):
        raise RequiresAuthException()


def api_require_admin(request: Request):
    if not request.session.get("is_admin"):
        raise StarletteHTTPException(status_code=401, detail="Unauthorized")


def check_password(password: str) -> bool:
    # An empty configured password disables login rather than accepting a blank one.
    if not settings.ADMIN_PASSWORD:
        return False
    return hmac.compare_digest(password.encode(), settings.ADMIN_PASSWORD.encode())


def log_password_config():
    """Log how ADMIN_PASSWORD was picked up, to debug "the password doesn't work".

    Never logs the password itself; its length is enough to spot most mistakes
    (e.g. compose expanding `pa$sword` in .env to `pa`).
    """
    password = settings.ADMIN_PASSWORD
    if "ADMIN_PASSWORD" not in os.environ:
        logger.warning("ADMIN_PASSWORD is not set; the admin password is the default 'changeme'")
        return
    if not password:
        logger.error("ADMIN_PASSWORD is set but empty; admin login is disabled")
        return
    logger.info("Admin password configured (%d characters)", len(password))
    if password != password.strip():
        logger.warning("ADMIN_PASSWORD has leading/trailing whitespace; it must be typed with it")
    if len(password) >= 2 and password[0] == password[-1] and password[0] in "\"'":
        logger.warning("ADMIN_PASSWORD is wrapped in quotes; they are part of the password")
