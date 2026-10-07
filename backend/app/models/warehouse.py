from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, utcnow
from app.models.types import JSONType, ZoneType


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(String(512), default="")
    length_m: Mapped[float]
    width_m: Mapped[float]
    height_m: Mapped[float]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    archived_at: Mapped[datetime | None]

    zones: Mapped[list["Zone"]] = relationship(back_populates="warehouse")


class Zone(Base):
    __tablename__ = "zones"
    __table_args__ = (UniqueConstraint("warehouse_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255), default="")
    type: Mapped[str] = mapped_column(String(16), default=ZoneType.storage)
    # [[x, y], ...] in warehouse metres, counter-clockwise, not closed
    polygon: Mapped[list] = mapped_column(JSONType)
    color: Mapped[str | None] = mapped_column(String(16))
    archived_at: Mapped[datetime | None]

    warehouse: Mapped[Warehouse] = relationship(back_populates="zones")
    shelves: Mapped[list["Shelf"]] = relationship(back_populates="zone")


class Shelf(Base):
    __tablename__ = "shelves"

    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    # (x_m, y_m) is the shelf centre; rotation is counter-clockwise around it
    x_m: Mapped[float]
    y_m: Mapped[float]
    rotation_deg: Mapped[float] = mapped_column(default=0.0)
    width_m: Mapped[float]
    depth_m: Mapped[float]
    height_m: Mapped[float]
    levels: Mapped[int]
    places_per_level: Mapped[int]
    archived_at: Mapped[datetime | None]

    zone: Mapped[Zone] = relationship(back_populates="shelves")
    cells: Mapped[list["Cell"]] = relationship(back_populates="shelf")


class Cell(Base):
    __tablename__ = "cells"

    id: Mapped[int] = mapped_column(primary_key=True)
    shelf_id: Mapped[int | None] = mapped_column(ForeignKey("shelves.id"), index=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"), index=True)
    address: Mapped[str] = mapped_column(String(64), index=True)
    level: Mapped[int | None]
    place: Mapped[int | None]
    polygon: Mapped[list] = mapped_column(JSONType)
    capacity: Mapped[int] = mapped_column(default=1)
    archived_at: Mapped[datetime | None]

    shelf: Mapped[Shelf | None] = relationship(back_populates="cells")
