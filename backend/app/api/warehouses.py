from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.core.db import utcnow
from app.models import Cell, ObjectType, Shelf, TrackedObject, Warehouse, Zone
from app.models.types import ObjectStatus
from app.schemas.warehouse import (
    CellOut,
    FloorCellsRequest,
    ShelfCreate,
    ShelfOut,
    ShelfUpdate,
    TwinObject,
    TwinOut,
    WarehouseCreate,
    WarehouseOut,
    WarehouseUpdate,
    ZoneCreate,
    ZoneOut,
    ZoneUpdate,
)
from app.services import layout, structure
from app.services.audit import audit

router = APIRouter(prefix="/api", tags=["structure"])

SHELF_GEOMETRY_FIELDS = {
    "x_m", "y_m", "rotation_deg", "width_m", "depth_m", "levels", "places_per_level", "code"
}


def _get_or_404(db, model, obj_id: int, what: str):
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "archived_at", None) is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{what} не найден(а)")
    return obj


def _reject(errors: list[str]) -> None:
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"errors": errors})


# --- Warehouses ---------------------------------------------------------------


@router.get("/warehouses", response_model=list[WarehouseOut])
def list_warehouses(db: DbSession, _: CurrentUser) -> list[Warehouse]:
    stmt = select(Warehouse).where(Warehouse.archived_at.is_(None)).order_by(Warehouse.id)
    return list(db.scalars(stmt))


@router.get("/warehouses/{warehouse_id}", response_model=WarehouseOut)
def get_warehouse(warehouse_id: int, db: DbSession, _: CurrentUser) -> Warehouse:
    return _get_or_404(db, Warehouse, warehouse_id, "Склад")


@router.post("/warehouses", response_model=WarehouseOut, status_code=status.HTTP_201_CREATED)
def create_warehouse(data: WarehouseCreate, db: DbSession, admin: AdminUser) -> Warehouse:
    wh = Warehouse(**data.model_dump())
    db.add(wh)
    db.flush()
    audit(db, admin, "create", "warehouse", wh.id, data.model_dump())
    db.commit()
    return wh


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseOut)
def update_warehouse(
    warehouse_id: int, data: WarehouseUpdate, db: DbSession, admin: AdminUser
) -> Warehouse:
    wh = _get_or_404(db, Warehouse, warehouse_id, "Склад")
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(wh, key, value)
    shelves = structure.active_shelves(db, wh.id)
    _reject(layout.validate_layout(
        wh.length_m, wh.width_m, [structure.to_geometry(s) for s in shelves]
    ))
    audit(db, admin, "update", "warehouse", wh.id, changes)
    db.commit()
    return wh


@router.delete("/warehouses/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_warehouse(warehouse_id: int, db: DbSession, admin: AdminUser) -> None:
    wh = _get_or_404(db, Warehouse, warehouse_id, "Склад")
    wh.archived_at = utcnow()
    audit(db, admin, "archive", "warehouse", wh.id)
    db.commit()


@router.get("/warehouses/{warehouse_id}/twin", response_model=TwinOut)
def get_twin(warehouse_id: int, db: DbSession, _: CurrentUser) -> TwinOut:
    wh = _get_or_404(db, Warehouse, warehouse_id, "Склад")
    zones = list(db.scalars(
        select(Zone).where(Zone.warehouse_id == wh.id, Zone.archived_at.is_(None))
    ))
    zone_ids = [z.id for z in zones]
    shelves = list(db.scalars(
        select(Shelf).where(Shelf.zone_id.in_(zone_ids), Shelf.archived_at.is_(None))
    ))
    cells = list(db.scalars(
        select(Cell).where(Cell.zone_id.in_(zone_ids), Cell.archived_at.is_(None))
    ))
    rows = db.execute(
        select(TrackedObject, ObjectType.code)
        .join(ObjectType, TrackedObject.type_id == ObjectType.id)
        .where(
            TrackedObject.current_zone_id.in_(zone_ids),
            TrackedObject.status.in_([ObjectStatus.active, ObjectStatus.missing]),
        )
    ).all()
    objects = [
        TwinObject(
            id=o.id, type_code=code, name=o.name, status=o.status, cell_id=o.current_cell_id,
            zone_id=o.current_zone_id, x_m=o.x_m, y_m=o.y_m, last_seen_at=o.last_seen_at,
        )
        for o, code in rows
    ]
    occupied = sorted({
        o.cell_id for o in objects if o.cell_id is not None and o.status == ObjectStatus.active
    })
    return TwinOut(
        warehouse=WarehouseOut.model_validate(wh),
        zones=[ZoneOut.model_validate(z) for z in zones],
        shelves=[ShelfOut.model_validate(s) for s in shelves],
        cells=[CellOut.model_validate(c) for c in cells],
        objects=objects,
        occupied_cell_ids=occupied,
    )


# --- Zones --------------------------------------------------------------------


@router.get("/zones", response_model=list[ZoneOut])
def list_zones(warehouse_id: int, db: DbSession, _: CurrentUser) -> list[Zone]:
    stmt = select(Zone).where(Zone.warehouse_id == warehouse_id, Zone.archived_at.is_(None))
    return list(db.scalars(stmt.order_by(Zone.code)))


@router.post("/zones", response_model=ZoneOut, status_code=status.HTTP_201_CREATED)
def create_zone(data: ZoneCreate, db: DbSession, admin: AdminUser) -> Zone:
    wh = _get_or_404(db, Warehouse, data.warehouse_id, "Склад")
    _reject(layout.validate_zone_polygon(wh.length_m, wh.width_m, data.polygon))
    zone = Zone(**data.model_dump())
    db.add(zone)
    db.flush()
    audit(db, admin, "create", "zone", zone.id, data.model_dump())
    db.commit()
    return zone


@router.patch("/zones/{zone_id}", response_model=ZoneOut)
def update_zone(zone_id: int, data: ZoneUpdate, db: DbSession, admin: AdminUser) -> Zone:
    zone = _get_or_404(db, Zone, zone_id, "Зона")
    changes = data.model_dump(exclude_unset=True)
    if "polygon" in changes:
        wh = db.get(Warehouse, zone.warehouse_id)
        _reject(layout.validate_zone_polygon(wh.length_m, wh.width_m, changes["polygon"]))
    for key, value in changes.items():
        setattr(zone, key, value)
    audit(db, admin, "update", "zone", zone.id, changes)
    db.commit()
    return zone


@router.delete("/zones/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_zone(zone_id: int, db: DbSession, admin: AdminUser) -> None:
    zone = _get_or_404(db, Zone, zone_id, "Зона")
    now = utcnow()
    zone.archived_at = now
    for shelf in zone.shelves:
        shelf.archived_at = shelf.archived_at or now
    structure.archive_cells(db, list(db.scalars(select(Cell).where(Cell.zone_id == zone.id))))
    audit(db, admin, "archive", "zone", zone.id)
    db.commit()


@router.post("/zones/{zone_id}/generate-floor-cells", response_model=list[CellOut])
def generate_floor_cells(
    zone_id: int, data: FloorCellsRequest, db: DbSession, admin: AdminUser
) -> list[Cell]:
    zone = _get_or_404(db, Zone, zone_id, "Зона")
    cells = structure.regenerate_floor_cells(db, zone, data.step_m)
    audit(db, admin, "generate_floor_cells", "zone", zone.id, {"step_m": data.step_m})
    db.commit()
    return cells


# --- Shelves ------------------------------------------------------------------


@router.get("/shelves", response_model=list[ShelfOut])
def list_shelves(warehouse_id: int, db: DbSession, _: CurrentUser) -> list[Shelf]:
    return sorted(structure.active_shelves(db, warehouse_id), key=lambda s: s.code)


@router.post("/shelves", response_model=ShelfOut, status_code=status.HTTP_201_CREATED)
def create_shelf(data: ShelfCreate, db: DbSession, admin: AdminUser) -> Shelf:
    zone = _get_or_404(db, Zone, data.zone_id, "Зона")
    wh = db.get(Warehouse, zone.warehouse_id)
    shelf = Shelf(**data.model_dump())
    _reject(structure.validate_shelf(db, wh, shelf))
    db.add(shelf)
    db.flush()
    structure.regenerate_shelf_cells(db, shelf)
    audit(db, admin, "create", "shelf", shelf.id, data.model_dump())
    db.commit()
    return shelf


@router.patch("/shelves/{shelf_id}", response_model=ShelfOut)
def update_shelf(shelf_id: int, data: ShelfUpdate, db: DbSession, admin: AdminUser) -> Shelf:
    shelf = _get_or_404(db, Shelf, shelf_id, "Стеллаж")
    changes = data.model_dump(exclude_unset=True)
    with db.no_autoflush:
        for key, value in changes.items():
            setattr(shelf, key, value)
        wh = db.get(Warehouse, shelf.zone.warehouse_id)
        errors = structure.validate_shelf(db, wh, shelf)
    if errors:
        db.rollback()
        _reject(errors)
    if SHELF_GEOMETRY_FIELDS & changes.keys():
        structure.regenerate_shelf_cells(db, shelf)
    audit(db, admin, "update", "shelf", shelf.id, changes)
    db.commit()
    return shelf


@router.delete("/shelves/{shelf_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_shelf(shelf_id: int, db: DbSession, admin: AdminUser) -> None:
    shelf = _get_or_404(db, Shelf, shelf_id, "Стеллаж")
    shelf.archived_at = utcnow()
    structure.archive_cells(db, list(shelf.cells))
    audit(db, admin, "archive", "shelf", shelf.id)
    db.commit()


@router.post("/shelves/{shelf_id}/generate-cells", response_model=list[CellOut])
def generate_cells(shelf_id: int, db: DbSession, admin: AdminUser) -> list[Cell]:
    shelf = _get_or_404(db, Shelf, shelf_id, "Стеллаж")
    cells = structure.regenerate_shelf_cells(db, shelf)
    audit(db, admin, "generate_cells", "shelf", shelf.id)
    db.commit()
    return cells


# --- Cells --------------------------------------------------------------------


@router.get("/cells", response_model=list[CellOut])
def list_cells(
    db: DbSession, _: CurrentUser, zone_id: int | None = None, shelf_id: int | None = None
) -> list[Cell]:
    stmt = select(Cell).where(Cell.archived_at.is_(None))
    if zone_id is not None:
        stmt = stmt.where(Cell.zone_id == zone_id)
    if shelf_id is not None:
        stmt = stmt.where(Cell.shelf_id == shelf_id)
    return list(db.scalars(stmt.order_by(Cell.address)))
