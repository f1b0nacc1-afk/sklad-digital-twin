"""Структура склада: геометрия стеллажей, генерация ячеек, валидация (ФТ-СКЛ-04/05/08)."""

import math
from dataclasses import dataclass

from shapely.geometry import Point, Polygon, box

Polygon2D = list[list[float]]

# Shelves may touch but not overlap; tolerance absorbs float noise on shared edges.
OVERLAP_TOLERANCE_M2 = 1e-6


@dataclass(frozen=True)
class ShelfGeometry:
    code: str
    x_m: float
    y_m: float
    width_m: float
    depth_m: float
    rotation_deg: float = 0.0


@dataclass(frozen=True)
class CellSpec:
    address: str
    level: int | None
    place: int | None
    polygon: Polygon2D


def _rotate(dx: float, dy: float, angle_rad: float) -> tuple[float, float]:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return dx * c - dy * s, dx * s + dy * c


def _local_rect(shelf: ShelfGeometry, x0: float, x1: float) -> Polygon2D:
    """Rectangle [x0, x1] along shelf width (local coords from the left edge), full depth."""
    a = math.radians(shelf.rotation_deg)
    half_w, half_d = shelf.width_m / 2, shelf.depth_m / 2
    corners = [(x0 - half_w, -half_d), (x1 - half_w, -half_d),
               (x1 - half_w, half_d), (x0 - half_w, half_d)]
    result = []
    for dx, dy in corners:
        rx, ry = _rotate(dx, dy, a)
        result.append([round(shelf.x_m + rx, 6), round(shelf.y_m + ry, 6)])
    return result


def shelf_footprint(shelf: ShelfGeometry) -> Polygon2D:
    return _local_rect(shelf, 0.0, shelf.width_m)


def cell_address(shelf_code: str, level: int, place: int) -> str:
    return f"{shelf_code}-{level:02d}-{place:02d}"


def generate_shelf_cells(
    shelf: ShelfGeometry, levels: int, places_per_level: int
) -> list[CellSpec]:
    """Cells of every level share the same top-view footprint; places split the shelf width."""
    if levels < 1 or places_per_level < 1:
        raise ValueError("levels and places_per_level must be >= 1")
    step = shelf.width_m / places_per_level
    footprints = [_local_rect(shelf, i * step, (i + 1) * step) for i in range(places_per_level)]
    return [
        CellSpec(cell_address(shelf.code, level, place), level, place, footprints[place - 1])
        for level in range(1, levels + 1)
        for place in range(1, places_per_level + 1)
    ]


def generate_floor_cells(zone_code: str, polygon: Polygon2D, step_m: float) -> list[CellSpec]:
    """Square grid cells fully inside the zone polygon, numbered row by row from the origin."""
    if step_m <= 0:
        raise ValueError("step_m must be positive")
    zone = Polygon(polygon)
    min_x, min_y, max_x, max_y = zone.bounds
    cells: list[CellSpec] = []
    n = 0
    y = min_y
    while y + step_m <= max_y + 1e-9:
        x = min_x
        while x + step_m <= max_x + 1e-9:
            square = box(x, y, x + step_m, y + step_m)
            if zone.buffer(1e-9).contains(square):
                n += 1
                coords = [[round(px, 6), round(py, 6)] for px, py in square.exterior.coords[:-1]]
                cells.append(CellSpec(f"{zone_code}-F-{n:02d}", None, None, coords))
            x += step_m
        y += step_m
    return cells


def validate_layout(
    length_m: float, width_m: float, shelves: list[ShelfGeometry]
) -> list[str]:
    """Return human-readable errors; empty list means the layout is valid."""
    errors: list[str] = []
    room = box(0, 0, length_m, width_m).buffer(1e-9)
    polys = [(s.code, Polygon(shelf_footprint(s))) for s in shelves]
    for code, poly in polys:
        if not room.contains(poly):
            errors.append(f"Стеллаж {code} выходит за границы помещения")
    for i, (code_a, a) in enumerate(polys):
        for code_b, b in polys[i + 1:]:
            if a.intersection(b).area > OVERLAP_TOLERANCE_M2:
                errors.append(f"Стеллажи {code_a} и {code_b} пересекаются")
    return errors


def validate_zone_polygon(length_m: float, width_m: float, polygon: Polygon2D) -> list[str]:
    errors: list[str] = []
    if len(polygon) < 3:
        return ["Полигон зоны должен содержать не менее 3 точек"]
    zone = Polygon(polygon)
    if not zone.is_valid or zone.area <= 0:
        errors.append("Полигон зоны некорректен (самопересечение или нулевая площадь)")
    elif not box(0, 0, length_m, width_m).buffer(1e-9).contains(zone):
        errors.append("Зона выходит за границы помещения")
    return errors


def point_in_polygon(x: float, y: float, polygon: Polygon2D) -> bool:
    return Polygon(polygon).buffer(1e-9).contains(Point(x, y))
