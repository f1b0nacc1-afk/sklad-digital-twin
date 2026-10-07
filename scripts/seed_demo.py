"""Демо-данные: склад 30×15 м (ТЗ, прил. А) и настольный макет 1,2×0,8 м (стенд А).

Запуск из корня репозитория:  uv run python scripts/seed_demo.py [--replace]
Повторный запуск не дублирует данные (склад ищется по названию); --replace пересоздаёт
демо-склады, если по ним ещё не было сканирований.
Геометрия макета берётся из cv/sim/stands/maquette_a.json — того же описания, что у
виртуального стенда.
"""

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import delete, func, or_, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.bootstrap import bootstrap  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Cell,
    Detection,
    ObjectEvent,
    ObjectType,
    OccupancySnapshot,
    Shelf,
    TrackedObject,
    Warehouse,
    Zone,
)
from app.models.types import EventType, ZoneType  # noqa: E402
from app.services import layout, structure  # noqa: E402


def rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


WAREHOUSE = {
    "name": "Склад №1",
    "address": "Демонстрационный",
    "size": (30, 15, 6),
    "zones": [
        ("A", "Зона A — хранение", ZoneType.storage, rect(0, 8, 22, 15), "#cfe8ff"),
        ("B", "Зона B — хранение", ZoneType.storage, rect(0, 0, 16, 6), "#d8f3dc"),
        ("C", "Зона C — погрузка", ZoneType.loading, rect(22, 0, 30, 6), "#ffe5b4"),
        ("P", "Проходы", ZoneType.aisle, rect(0, 6, 30, 8), "#eeeeee"),
    ],
    # code, zone, x, y, rot, width, depth, height, levels, places
    "shelves": [
        ("A-01", "A", 4, 11.5, 0, 5, 1.2, 4, 4, 3),
        ("A-02", "A", 11, 11.5, 0, 5, 1.2, 4, 4, 3),
        ("A-03", "A", 18, 11.5, 0, 5, 1.2, 4, 4, 3),
        ("B-01", "B", 4, 3, 0, 5, 1.2, 4, 4, 3),
        ("B-02", "B", 10, 3, 0, 5, 1.2, 4, 4, 3),
    ],
    "floor_cells": {"C": 2.0},
}

def maquette_spec(path: Path = ROOT / "cv" / "sim" / "stands" / "maquette_a.json") -> dict:
    s = json.loads(path.read_text(encoding="utf-8-sig"))
    return {
        "name": s["name"],
        "address": s["address"],
        "size": tuple(s["size"]),
        "zones": [(z["code"], z["name"], ZoneType(z["type"]), z["polygon"], z["color"])
                  for z in s["zones"]],
        "shelves": [(sh["code"], sh["zone"], sh["x"], sh["y"], sh["rotation_deg"], sh["width"],
                     sh["depth"], sh["height"], sh["levels"], sh["places"])
                    for sh in s["shelves"]],
        "floor_cells": s["floor_cells"],
    }


def delete_warehouse(db: Session, wh: Warehouse) -> None:
    zone_ids = list(db.scalars(select(Zone.id).where(Zone.warehouse_id == wh.id)))
    used = db.scalar(select(func.count()).select_from(Detection)
                     .where(Detection.zone_id.in_(zone_ids)))
    used += db.scalar(select(func.count()).select_from(OccupancySnapshot)
                      .where(OccupancySnapshot.zone_id.in_(zone_ids)))
    if used:
        raise SystemExit(f"{wh.name}: есть результаты сканирований, пересоздание отменено")
    cell_ids = select(Cell.id).where(Cell.zone_id.in_(zone_ids))
    object_ids = select(TrackedObject.id).where(or_(TrackedObject.current_zone_id.in_(zone_ids),
                                                    TrackedObject.current_cell_id.in_(cell_ids)))
    db.execute(delete(ObjectEvent).where(ObjectEvent.object_id.in_(object_ids)))
    db.execute(delete(TrackedObject).where(TrackedObject.id.in_(object_ids)))
    db.execute(delete(Cell).where(Cell.zone_id.in_(zone_ids)))
    db.execute(delete(Shelf).where(Shelf.zone_id.in_(zone_ids)))
    db.execute(delete(Zone).where(Zone.id.in_(zone_ids)))
    db.delete(wh)
    db.flush()
    print(f"  - {wh.name} удалён (id={wh.id})")


def seed_warehouse(db: Session, spec: dict, objects: int, replace: bool = False) -> Warehouse:
    existing = db.scalar(select(Warehouse).where(Warehouse.name == spec["name"]))
    if existing and replace:
        delete_warehouse(db, existing)
    elif existing:
        print(f"  = {spec['name']} уже есть (id={existing.id})")
        return existing

    length, width, height = spec["size"]
    wh = Warehouse(name=spec["name"], address=spec["address"],
                   length_m=length, width_m=width, height_m=height)
    db.add(wh)
    db.flush()

    zones: dict[str, Zone] = {}
    for code, name, ztype, polygon, color in spec["zones"]:
        errors = layout.validate_zone_polygon(length, width, polygon)
        assert not errors, (code, errors)
        zones[code] = Zone(warehouse_id=wh.id, code=code, name=name, type=ztype,
                           polygon=polygon, color=color)
        db.add(zones[code])
    db.flush()

    shelves = []
    for code, zone, x, y, rot, w, d, h, levels, places in spec["shelves"]:
        shelves.append(Shelf(zone_id=zones[zone].id, code=code, x_m=x, y_m=y, rotation_deg=rot,
                             width_m=w, depth_m=d, height_m=h, levels=levels,
                             places_per_level=places))
    errors = layout.validate_layout(length, width, [structure.to_geometry(s) for s in shelves])
    assert not errors, errors
    db.add_all(shelves)
    db.flush()
    for shelf in shelves:
        structure.regenerate_shelf_cells(db, shelf)
    for zone_code, step in spec["floor_cells"].items():
        structure.regenerate_floor_cells(db, zones[zone_code], step)
    db.flush()

    _seed_objects(db, list(zones.values()), objects)
    db.commit()
    print(f"  + {spec['name']} (id={wh.id})")
    return wh


def _seed_objects(db: Session, zones: list[Zone], count: int) -> None:
    rng = random.Random(42)
    zone_ids = [z.id for z in zones]
    cells = list(db.scalars(select(Cell).where(Cell.zone_id.in_(zone_ids))))
    # From above only the top level of a shelf is visible.
    top = {}
    for c in cells:
        key = (c.shelf_id, c.place) if c.shelf_id else ("floor", c.id)
        if key not in top or (c.level or 0) > (top[key].level or 0):
            top[key] = c
    candidates = rng.sample(list(top.values()), min(count, len(top)))
    types = {t.code: t for t in db.scalars(select(ObjectType))}
    for i, cell in enumerate(candidates, start=1):
        type_code = "pallet" if cell.shelf_id is None else rng.choice(["box", "box", "container"])
        xs = [p[0] for p in cell.polygon]
        ys = [p[1] for p in cell.polygon]
        obj = TrackedObject(
            type_id=types[type_code].id,
            name=f"{types[type_code].name} №{i}",
            barcode=f"DEMO{i:05d}" if i % 3 == 0 else None,
            current_cell_id=cell.id,
            current_zone_id=cell.zone_id,
            x_m=sum(xs) / len(xs),
            y_m=sum(ys) / len(ys),
        )
        db.add(obj)
        db.flush()
        db.add(ObjectEvent(object_id=obj.id, event_type=EventType.appeared, to_cell_id=cell.id))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--replace", action="store_true", help="пересоздать демо-склады")
    a = p.parse_args()
    with SessionLocal() as db:
        bootstrap(db)
        seed_warehouse(db, WAREHOUSE, objects=25, replace=a.replace)
        seed_warehouse(db, maquette_spec(), objects=12, replace=a.replace)
    print("seed_demo: ok")


if __name__ == "__main__":
    main()
