from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import check_password
from app.database import get_db
from app.models import Project

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


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
async def login_submit(request: Request, password: str = Form(...)):
    if check_password(password):
        request.session["is_admin"] = True
        return RedirectResponse(url="/admin", status_code=302)
    return templates.TemplateResponse(
        request, "login.html", {"error": "Invalid password"}
    )


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)
