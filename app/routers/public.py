import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import check_password
from app.config import settings
from app.database import get_db
from app.models import Project

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["git_hash"] = settings.GIT_HASH


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return templates.TemplateResponse(
        request, "index.html", {"projects": projects}
    )


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_view(
    project_id: int, request: Request, db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse(url="/", status_code=302)
    catalog = [
        {
            "letter": s.letter,
            "name": s.name,
            "numbers": sorted({loc.number for loc in s.number_locations}),
        }
        for s in project.sprues
        if s.number_locations
    ]
    return templates.TemplateResponse(
        request, "project_view.html",
        {"project": project, "catalog": catalog},
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, password: str = Form("")):
    # Default "" so a blank submission gets the login page back, not a 422.
    client = request.client.host if request.client else "unknown"
    if check_password(password):
        logger.info("Admin login succeeded from %s", client)
        request.session["is_admin"] = True
        return RedirectResponse(url="/admin", status_code=302)
    if not settings.ADMIN_PASSWORD:
        logger.warning("Admin login failed from %s: ADMIN_PASSWORD is empty, login is disabled", client)
    else:
        logger.warning(
            "Admin login failed from %s: wrong password (%d characters entered, configured password has %d)",
            client, len(password), len(settings.ADMIN_PASSWORD),
        )
    return templates.TemplateResponse(
        request, "login.html", {"error": "Invalid password"}
    )


@router.get("/logout")
async def logout(request: Request):
    if request.session.get("is_admin"):
        logger.info("Admin logout from %s", request.client.host if request.client else "unknown")
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)
