from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    sprues: Mapped[list["Sprue"]] = relationship(
        "Sprue", back_populates="project", cascade="all, delete-orphan"
    )


class Sprue(Base):
    __tablename__ = "sprues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    letter: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    image_filename: Mapped[str] = mapped_column(String(200), nullable=False)
    ocr_profile: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Display crop as fractions (0.0-1.0) of the photo; the stored image is never modified.
    crop_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    crop_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    crop_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    crop_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="sprues")
    number_locations: Mapped[list["NumberLocation"]] = relationship(
        "NumberLocation", back_populates="sprue", cascade="all, delete-orphan"
    )


class NumberLocation(Base):
    __tablename__ = "number_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sprue_id: Mapped[int] = mapped_column(ForeignKey("sprues.id"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0)

    sprue: Mapped["Sprue"] = relationship("Sprue", back_populates="number_locations")
