from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, utcnow
from app.models.types import JSONType, ObjectStatus, ScanStatus


class TrackedObject(Base):
    __tablename__ = "objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    type_id: Mapped[int] = mapped_column(ForeignKey("object_types.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    category: Mapped[str] = mapped_column(String(128), default="")
    barcode: Mapped[str | None] = mapped_column(String(128), index=True)
    size_l: Mapped[float | None]
    size_w: Mapped[float | None]
    size_h: Mapped[float | None]
    weight_kg: Mapped[float | None]
    allowed_zone_ids: Mapped[list] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(16), default=ObjectStatus.active, index=True)
    current_cell_id: Mapped[int | None] = mapped_column(ForeignKey("cells.id"), index=True)
    current_zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"), index=True)
    x_m: Mapped[float | None]
    y_m: Mapped[float | None]
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    missed_scans: Mapped[int] = mapped_column(default=0)


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default=ScanStatus.queued, index=True)
    reject_reason: Mapped[str | None] = mapped_column(String(512))
    error: Mapped[str | None]
    image_path: Mapped[str | None] = mapped_column(String(512))
    preview_path: Mapped[str | None] = mapped_column(String(512))
    annotated_path: Mapped[str | None] = mapped_column(String(512))
    width: Mapped[int | None]
    height: Mapped[int | None]
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"))
    started_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    finished_at: Mapped[datetime | None]
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    type_id: Mapped[int] = mapped_column(ForeignKey("object_types.id"))
    confidence: Mapped[float]
    # bbox centre (x, y) and size in pixels
    bbox_x: Mapped[float]
    bbox_y: Mapped[float]
    bbox_w: Mapped[float]
    bbox_h: Mapped[float]
    x_m: Mapped[float | None]
    y_m: Mapped[float | None]
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"))
    cell_id: Mapped[int | None] = mapped_column(ForeignKey("cells.id"))
    object_id: Mapped[int | None] = mapped_column(ForeignKey("objects.id"), index=True)
    barcode: Mapped[str | None] = mapped_column(String(128))
    is_manual: Mapped[bool] = mapped_column(default=False)
    is_rejected: Mapped[bool] = mapped_column(default=False)


class ObjectEvent(Base):
    __tablename__ = "object_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(16), index=True)
    from_cell_id: Mapped[int | None] = mapped_column(ForeignKey("cells.id"))
    to_cell_id: Mapped[int | None] = mapped_column(ForeignKey("cells.id"))
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_assumed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class OccupancySnapshot(Base):
    __tablename__ = "occupancy_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id"), index=True)
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"))
    shelf_id: Mapped[int | None] = mapped_column(ForeignKey("shelves.id"))
    total_cells: Mapped[int]
    occupied_cells: Mapped[int]
    objects_count: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSONType)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
