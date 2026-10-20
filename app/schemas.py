from datetime import datetime

from pydantic import BaseModel, Field, model_validator


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


class CropBox(BaseModel):
    """Display crop as fractions of the photo (0.0-1.0)."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0.02, le=1)
    height: float = Field(gt=0.02, le=1)

    @model_validator(mode="after")
    def _inside_image(self):
        # Small tolerance for float rounding when the box is dragged to the very edge.
        if self.x + self.width > 1.001 or self.y + self.height > 1.001:
            raise ValueError("crop box extends past the image")
        return self

    @classmethod
    def from_sprue(cls, sprue) -> "CropBox | None":
        if sprue.crop_w is None:
            return None
        return cls(x=sprue.crop_x, y=sprue.crop_y, width=sprue.crop_w, height=sprue.crop_h)

    def apply_to(self, sprue) -> None:
        sprue.crop_x, sprue.crop_y = self.x, self.y
        sprue.crop_w, sprue.crop_h = self.width, self.height

    @classmethod
    def around(cls, detections: list[dict], margin: float = 0.03, min_count: int = 3) -> "CropBox | None":
        """
        Bounding box of all detections (relative coords) plus `margin`, clamped
        to the image. The labels sit on the sprue frame, so this frames the
        sprue. Same rule as the editor's "Fit to Numbers" (editor.js). None with
        fewer than `min_count` detections, whose box would cut off most of it.
        """
        if len(detections) < min_count:
            return None
        x1 = max(0.0, min(d["x"] for d in detections) - margin)
        y1 = max(0.0, min(d["y"] for d in detections) - margin)
        x2 = min(1.0, max(d["x"] + d["width"] for d in detections) + margin)
        y2 = min(1.0, max(d["y"] + d["height"] for d in detections) + margin)
        try:
            return cls(x=round(x1, 4), y=round(y1, 4), width=round(x2 - x1, 4), height=round(y2 - y1, 4))
        except ValueError:  # degenerate (e.g. all detections in one spot)
            return None


class SprueUpdate(BaseModel):
    letter: str | None = None
    name: str | None = None
    # Send null to remove the crop; omit the field to leave it unchanged.
    crop: CropBox | None = None


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
    crop: CropBox | None = None
    locations: list[NumberLocationOut]
