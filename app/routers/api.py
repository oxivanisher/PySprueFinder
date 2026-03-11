import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import api_require_admin
from app.config import settings
from app.database import get_db
from app.models import NumberLocation, Project, Sprue
from app.ocr import PROFILES, get_debug_preview, process_image
from app.schemas import NumberLocationCreate, NumberLocationOut, NumberLocationUpdate, SearchResult

router = APIRouter()


@router.get("/projects/{project_id}/search", response_model=list[SearchResult])
async def search(project_id: int, q: str = "", db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    q = q.strip()
    if not q:
        return []

    match = re.fullmatch(r"([A-Za-z]*)(\d+)", q)
    if not match:
        return []

    letter_prefix = match.group(1).upper()
    number = int(match.group(2))

    sprues = db.query(Sprue).filter(Sprue.project_id == project_id).all()
    if letter_prefix:
        sprues = [s for s in sprues if s.letter.upper() == letter_prefix]

    results = []
    for sprue in sprues:
        locations = (
            db.query(NumberLocation)
            .filter(NumberLocation.sprue_id == sprue.id, NumberLocation.number == number)
            .all()
        )
        if locations:
            results.append(
                SearchResult(
                    sprue_id=sprue.id,
                    sprue_letter=sprue.letter,
                    sprue_name=sprue.name,
                    image_filename=sprue.image_filename,
                    locations=[NumberLocationOut.model_validate(loc) for loc in locations],
                )
            )

    return results


@router.get("/sprues/{sprue_id}/numbers", response_model=list[NumberLocationOut])
async def get_numbers(sprue_id: int, db: Session = Depends(get_db)):
    sprue = db.query(Sprue).filter(Sprue.id == sprue_id).first()
    if not sprue:
        raise HTTPException(status_code=404, detail="Sprue not found")
    return sprue.number_locations


@router.post("/sprues/{sprue_id}/numbers", response_model=NumberLocationOut)
async def add_number(
    sprue_id: int,
    payload: NumberLocationCreate,
    db: Session = Depends(get_db),
    request: Request = None,
    _=Depends(api_require_admin),
):
    sprue = db.query(Sprue).filter(Sprue.id == sprue_id).first()
    if not sprue:
        raise HTTPException(status_code=404, detail="Sprue not found")
    loc = NumberLocation(sprue_id=sprue_id, **payload.model_dump())
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


@router.put("/numbers/{number_id}", response_model=NumberLocationOut)
async def update_number(
    number_id: int,
    payload: NumberLocationUpdate,
    db: Session = Depends(get_db),
    _=Depends(api_require_admin),
):
    loc = db.query(NumberLocation).filter(NumberLocation.id == number_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Number not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(loc, field, value)
    db.commit()
    db.refresh(loc)
    return loc


@router.delete("/numbers/{number_id}")
async def delete_number(
    number_id: int,
    db: Session = Depends(get_db),
    _=Depends(api_require_admin),
):
    loc = db.query(NumberLocation).filter(NumberLocation.id == number_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Number not found")
    db.delete(loc)
    db.commit()
    return {"ok": True}


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    _=Depends(api_require_admin),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # Remove image files
    for sprue in project.sprues:
        filepath = os.path.join(settings.UPLOAD_DIR, sprue.image_filename)
        if os.path.exists(filepath):
            os.remove(filepath)
    db.delete(project)
    db.commit()
    return {"ok": True}


@router.delete("/sprues/{sprue_id}")
async def delete_sprue(
    sprue_id: int,
    db: Session = Depends(get_db),
    _=Depends(api_require_admin),
):
    sprue = db.query(Sprue).filter(Sprue.id == sprue_id).first()
    if not sprue:
        raise HTTPException(status_code=404, detail="Sprue not found")
    filepath = os.path.join(settings.UPLOAD_DIR, sprue.image_filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    db.delete(sprue)
    db.commit()
    return {"ok": True}


@router.post("/sprues/{sprue_id}/reprocess")
async def reprocess_sprue(
    sprue_id: int,
    profile: str = "auto",
    db: Session = Depends(get_db),
    _=Depends(api_require_admin),
):
    if profile not in PROFILES:
        raise HTTPException(status_code=400, detail=f"Unknown profile '{profile}'")
    sprue = db.query(Sprue).filter(Sprue.id == sprue_id).first()
    if not sprue:
        raise HTTPException(status_code=404, detail="Sprue not found")

    db.query(NumberLocation).filter(NumberLocation.sprue_id == sprue_id).delete()
    db.commit()

    filepath = os.path.join(settings.UPLOAD_DIR, sprue.image_filename)
    detections = process_image(filepath, profile=profile)

    for det in detections:
        db.add(NumberLocation(
            sprue_id=sprue_id,
            number=det["number"],
            x=det["x"],
            y=det["y"],
            width=det["width"],
            height=det["height"],
            confidence=det["confidence"],
        ))
    sprue.ocr_profile = profile
    db.commit()

    return {"ok": True, "count": len(detections), "profile": profile}


@router.get("/sprues/{sprue_id}/ocr-preview")
async def ocr_preview(
    sprue_id: int,
    profile: str = "auto",
    db: Session = Depends(get_db),
    _=Depends(api_require_admin),
):
    if profile not in PROFILES:
        raise HTTPException(status_code=400, detail=f"Unknown profile '{profile}'")
    sprue = db.query(Sprue).filter(Sprue.id == sprue_id).first()
    if not sprue:
        raise HTTPException(status_code=404, detail="Sprue not found")

    filepath = os.path.join(settings.UPLOAD_DIR, sprue.image_filename)
    jpeg_bytes = get_debug_preview(filepath, profile=profile)
    return Response(content=jpeg_bytes, media_type="image/jpeg")
