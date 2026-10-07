from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.types import ZoneType

Point2D = list[float]


class WarehouseBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: str = ""
    length_m: float = Field(gt=0)
    width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)


class WarehouseCreate(WarehouseBase):
    pass


class WarehouseUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    length_m: float | None = Field(default=None, gt=0)
    width_m: float | None = Field(default=None, gt=0)
    height_m: float | None = Field(default=None, gt=0)


class WarehouseOut(WarehouseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    archived_at: datetime | None


class ZoneBase(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = ""
    type: ZoneType = ZoneType.storage
    polygon: list[Point2D] = Field(min_length=3)
    color: str | None = None


class ZoneCreate(ZoneBase):
    warehouse_id: int


class ZoneUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    type: ZoneType | None = None
    polygon: list[Point2D] | None = Field(default=None, min_length=3)
    color: str | None = None


class ZoneOut(ZoneBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warehouse_id: int


class ShelfBase(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    x_m: float
    y_m: float
    rotation_deg: float = 0.0
    width_m: float = Field(gt=0)
    depth_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    levels: int = Field(ge=1, le=50)
    places_per_level: int = Field(ge=1, le=100)


class ShelfCreate(ShelfBase):
    zone_id: int


class ShelfUpdate(BaseModel):
    code: str | None = None
    x_m: float | None = None
    y_m: float | None = None
    rotation_deg: float | None = None
    width_m: float | None = Field(default=None, gt=0)
    depth_m: float | None = Field(default=None, gt=0)
    height_m: float | None = Field(default=None, gt=0)
    levels: int | None = Field(default=None, ge=1, le=50)
    places_per_level: int | None = Field(default=None, ge=1, le=100)


class ShelfOut(ShelfBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    zone_id: int


class CellOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shelf_id: int | None
    zone_id: int
    address: str
    level: int | None
    place: int | None
    polygon: list[Point2D]
    capacity: int


class FloorCellsRequest(BaseModel):
    step_m: float = Field(gt=0)


class TwinObject(BaseModel):
    id: int
    type_code: str
    name: str
    status: str
    cell_id: int | None
    zone_id: int | None
    x_m: float | None
    y_m: float | None
    last_seen_at: datetime


class TwinOut(BaseModel):
    warehouse: WarehouseOut
    zones: list[ZoneOut]
    shelves: list[ShelfOut]
    cells: list[CellOut]
    objects: list[TwinObject]
    occupied_cell_ids: list[int]
