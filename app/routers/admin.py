import os
import uuid
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import settings
from app.database import get_db
from app.models import NumberLocation, Project, Sprue
from app.ocr import process_image
from app.schemas import CropBox, NumberLocationOut

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["git_hash"] = settings.GIT_HASH


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return templates.TemplateResponse(
        request, "admin/dashboard.html", {"projects": projects}
    )


@router.get("/projects/new", response_class=HTMLResponse)
async def new_project_page(request: Request, _=Depends(require_admin)):
    return templates.TemplateResponse(
        request, "admin/project_form.html", {"project": None, "error": None}
    )


@router.post("/projects/new", response_class=HTMLResponse)
async def create_project(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    name = name.strip()
    if not name:
        return templates.TemplateResponse(
            request, "admin/project_form.html",
            {"project": None, "error": "Name is required"},
        )
    project = Project(name=name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return RedirectResponse(url=f"/admin/projects/{project.id}", status_code=302)


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def edit_project(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse(url="/admin", status_code=302)
    return templates.TemplateResponse(
        request, "admin/project_edit.html", {"project": project}
    )


@router.post("/projects/{project_id}/name", response_class=HTMLResponse)
async def update_project_name(
    project_id: int,
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse(url="/admin", status_code=302)
    name = name.strip()
    if name:
        project.name = name
        db.commit()
    return RedirectResponse(url=f"/admin/projects/{project_id}", status_code=302)


@router.post("/projects/{project_id}/sprues", response_class=HTMLResponse)
async def upload_sprue(
    project_id: int,
    request: Request,
    letter: str = Form(...),
    name: str = Form(""),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    profile = "auto"
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse(url="/admin", status_code=302)

    def error_page(message: str):
        return templates.TemplateResponse(
            request, "admin/project_edit.html", {"project": project, "error": message},
        )

    # Validate extension
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    ext = os.path.splitext(image.filename or "")[1].lower()
    if ext not in allowed:
        return error_page(f"Invalid file type '{ext}'. Allowed: {', '.join(sorted(allowed))}")

    contents = await image.read()
    try:
        pil_img = Image.open(BytesIO(contents))
        # Phone photos are stored sensor-side-up with an EXIF rotation flag;
        # bake the rotation in so the stored image (and OCR) is upright.
        pil_img = ImageOps.exif_transpose(pil_img).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return error_page("Could not read the uploaded image.")

    # Downscale if needed
    max_px = settings.MAX_UPLOAD_PX
    w, h = pil_img.size
    if w > max_px or h > max_px:
        scale = min(max_px / w, max_px / h)
        pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = os.path.join(settings.UPLOAD_DIR, filename)
    pil_img.save(filepath, "JPEG", quality=90)

    # Run OCR (CPU-bound; offload to a thread so it doesn't block the event loop)
    try:
        detections, effective_profile = await run_in_threadpool(process_image, filepath, profile=profile)
    except Exception:
        os.remove(filepath)
        raise

    # Save to DB
    sprue = Sprue(
        project_id=project_id,
        letter=letter.strip().upper(),
        name=name.strip() or None,
        image_filename=filename,
        ocr_profile=effective_profile,
    )
    if crop := CropBox.around(detections):
        crop.apply_to(sprue)
    db.add(sprue)
    db.commit()
    db.refresh(sprue)

    for det in detections:
        loc = NumberLocation(
            sprue_id=sprue.id,
            number=det["number"],
            x=det["x"],
            y=det["y"],
            width=det["width"],
            height=det["height"],
            confidence=det["confidence"],
        )
        db.add(loc)
    db.commit()

    return RedirectResponse(url=f"/admin/sprues/{sprue.id}", status_code=302)


@router.get("/sprues/{sprue_id}", response_class=HTMLResponse)
async def edit_sprue(
    sprue_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    sprue = db.query(Sprue).filter(Sprue.id == sprue_id).first()
    if not sprue:
        return RedirectResponse(url="/admin", status_code=302)
    locations_json = [
        NumberLocationOut.model_validate(loc).model_dump()
        for loc in sprue.number_locations
    ]
    return templates.TemplateResponse(
        request, "admin/sprue_edit.html",
        {
            "sprue": sprue,
            "locations_json": locations_json,
            "crop": crop.model_dump() if (crop := CropBox.from_sprue(sprue)) else None,
            "project": sprue.project,
        },
    )
