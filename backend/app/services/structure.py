"""Операции над структурой склада в БД поверх чистой геометрии из layout.py."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import Cell, Shelf, Warehouse, Zone
from app.services import layout


def to_geometry(shelf: Shelf) -> layout.ShelfGeometry:
    return layout.ShelfGeometry(
        code=shelf.code,
        x_m=shelf.x_m,
        y_m=shelf.y_m,
        width_m=shelf.width_m,
        depth_m=shelf.depth_m,
        rotation_deg=shelf.rotation_deg,
    )


def active_shelves(db: Session, warehouse_id: int) -> list[Shelf]:
    stmt = (
        select(Shelf)
        .join(Zone, Shelf.zone_id == Zone.id)
        .where(Zone.warehouse_id == warehouse_id, Shelf.archived_at.is_(None))
    )
    return list(db.scalars(stmt))


def validate_shelf(db: Session, warehouse: Warehouse, candidate: Shelf) -> list[str]:
    others = [s for s in active_shelves(db, warehouse.id) if s.id != candidate.id]
    return layout.validate_layout(
        warehouse.length_m, warehouse.width_m, [to_geometry(s) for s in [*others, candidate]]
    )


def archive_cells(db: Session, cells: list[Cell]) -> None:
    """Cells are archived, never deleted: history keeps referring to them (ФТ-СКЛ-09)."""
    now = utcnow()
    for cell in cells:
        if cell.archived_at is None:
            cell.archived_at = now


def regenerate_shelf_cells(db: Session, shelf: Shelf) -> list[Cell]:
    existing = db.scalars(
        select(Cell).where(Cell.shelf_id == shelf.id, Cell.archived_at.is_(None))
    ).all()
    archive_cells(db, list(existing))
    specs = layout.generate_shelf_cells(to_geometry(shelf), shelf.levels, shelf.places_per_level)
    cells = [
        Cell(
            shelf_id=shelf.id,
            zone_id=shelf.zone_id,
            address=s.address,
            level=s.level,
            place=s.place,
            polygon=s.polygon,
        )
        for s in specs
    ]
    db.add_all(cells)
    return cells


def regenerate_floor_cells(db: Session, zone: Zone, step_m: float) -> list[Cell]:
    existing = db.scalars(
        select(Cell).where(
            Cell.zone_id == zone.id, Cell.shelf_id.is_(None), Cell.archived_at.is_(None)
        )
    ).all()
    archive_cells(db, list(existing))
    specs = layout.generate_floor_cells(zone.code, zone.polygon, step_m)
    cells = [Cell(zone_id=zone.id, address=s.address, polygon=s.polygon) for s in specs]
    db.add_all(cells)
    return cells
