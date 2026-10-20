import hmac

from fastapi import Request
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings


class RequiresAuthException(Exception):
    pass


def require_admin(request: Request):
    if not request.session.get("is_admin"):
        raise RequiresAuthException()


def api_require_admin(request: Request):
    if not request.session.get("is_admin"):
        raise StarletteHTTPException(status_code=401, detail="Unauthorized")


def check_password(password: str) -> bool:
    return hmac.compare_digest(password.encode(), settings.ADMIN_PASSWORD.encode())
