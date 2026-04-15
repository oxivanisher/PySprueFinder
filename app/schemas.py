from datetime import datetime

from pydantic import BaseModel


class NumberLocationBase(BaseModel):
    number: int
    x: float
    y: float
    width: float
    height: float
    confidence: int = 0


class NumberLocationCreate(NumberLocationBase):
    pass


class NumberLocationUpdate(BaseModel):
    number: int | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    confidence: int | None = None


class NumberLocationOut(NumberLocationBase):
    id: int
    sprue_id: int

    model_config = {"from_attributes": True}


class SprueUpdate(BaseModel):
    letter: str | None = None
    name: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None


class SprueBase(BaseModel):
    letter: str
    name: str | None = None


class SprueOut(SprueBase):
    id: int
    project_id: int
    image_filename: str
    ocr_profile: str | None = None
    created_at: datetime
    number_locations: list[NumberLocationOut] = []

    model_config = {"from_attributes": True}


class ProjectBase(BaseModel):
    name: str


class ProjectOut(ProjectBase):
    id: int
    created_at: datetime
    sprues: list[SprueOut] = []

    model_config = {"from_attributes": True}


class SearchResult(BaseModel):
    sprue_id: int
    sprue_letter: str
    sprue_name: str | None
    image_filename: str
    locations: list[NumberLocationOut]
