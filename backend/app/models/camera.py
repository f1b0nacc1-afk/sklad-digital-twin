from datetime import datetime

from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, utcnow
from app.models.types import CameraStatus, JSONType
from app.models.warehouse import Zone

camera_zones = Table(
    "camera_zones",
    Base.metadata,
    Column("camera_id", ForeignKey("cameras.id", ondelete="CASCADE"), primary_key=True),
    Column("zone_id", ForeignKey("zones.id", ondelete="CASCADE"), primary_key=True),
)


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    vendor: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    serial: Mapped[str] = mapped_column(String(64), default="")
    # basler | hikrobot | file | video | rtsp
    connection: Mapped[str] = mapped_column(String(16), default="file")
    params: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(16), default=CameraStatus.unknown)
    last_frame_at: Mapped[datetime | None]

    zones: Mapped[list[Zone]] = relationship(secondary=camera_zones)


class CameraCalibration(Base):
    __tablename__ = "camera_calibrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), index=True)
    camera_matrix: Mapped[list | None] = mapped_column(JSONType)
    dist_coeffs: Mapped[list | None] = mapped_column(JSONType)
    homography: Mapped[list | None] = mapped_column(JSONType)
    # [{"px": [u, v], "world": [x, y]}, ...]
    reference_points: Mapped[list] = mapped_column(JSONType, default=list)
    reprojection_error: Mapped[float | None]
    valid_from: Mapped[datetime] = mapped_column(default=utcnow)
    is_active: Mapped[bool] = mapped_column(default=True)
