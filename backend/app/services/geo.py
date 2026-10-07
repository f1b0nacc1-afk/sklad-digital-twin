"""Геопривязка (ПС-3): пиксели -> метры склада -> зона / ячейка (ФТ-ЛОК-01…06, ФТ-КАМ-05)."""

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree

Polygon2D = list[list[float]]
ViewMode = Literal["top", "oblique"]


@dataclass(frozen=True)
class HomographyResult:
    matrix: list[list[float]]
    rmse_m: float
    per_point_error_m: list[float]


def compute_homography(
    px_points: list[list[float]], world_points: list[list[float]]
) -> HomographyResult:
    """Fit image->floor homography from >= 4 reference points; error is reported in metres."""
    if len(px_points) != len(world_points):
        raise ValueError("px_points and world_points must have the same length")
    if len(px_points) < 4:
        raise ValueError("at least 4 reference points are required")
    src = np.asarray(px_points, dtype=np.float64)
    dst = np.asarray(world_points, dtype=np.float64)
    matrix, _ = cv2.findHomography(src, dst, method=0)
    if matrix is None:
        raise ValueError("homography is degenerate (points are collinear?)")
    projected = pixel_to_world(matrix, px_points)
    errors = np.linalg.norm(np.asarray(projected) - dst, axis=1)
    return HomographyResult(
        matrix=matrix.tolist(),
        rmse_m=float(np.sqrt(np.mean(errors**2))),
        per_point_error_m=[float(e) for e in errors],
    )


def pixel_to_world(
    homography: list[list[float]] | np.ndarray, points: list[list[float]]
) -> list[list[float]]:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    h = np.asarray(homography, dtype=np.float64)
    return cv2.perspectiveTransform(pts, h).reshape(-1, 2).tolist()


def undistort_points(
    points: list[list[float]], camera_matrix: list[list[float]], dist_coeffs: list[float]
) -> list[list[float]]:
    """Remove lens distortion, keeping pixel coordinates (P = K)."""
    k = np.asarray(camera_matrix, dtype=np.float64)
    d = np.asarray(dist_coeffs, dtype=np.float64)
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.undistortPoints(pts, k, d, P=k).reshape(-1, 2).tolist()


def anchor_point(cx: float, cy: float, w: float, h: float, view: ViewMode = "top") -> list[float]:
    """Top view: bbox centre. Oblique view: bottom-edge midpoint (floor contact)."""
    if view == "top":
        return [cx, cy]
    return [cx, cy + h / 2]


@dataclass(frozen=True)
class AreaRef:
    id: int
    polygon: Polygon2D
    level: int | None = None
    zone_id: int | None = None


@dataclass(frozen=True)
class Location:
    zone_id: int | None
    cell_id: int | None

    @property
    def is_addressed(self) -> bool:
        return self.cell_id is not None


class Locator:
    """Point-in-polygon lookup over zones and cells of one warehouse."""

    def __init__(self, zones: list[AreaRef], cells: list[AreaRef]):
        self._zones = zones
        self._cells = cells
        self._zone_polys = [Polygon(z.polygon) for z in zones]
        self._cell_polys = [Polygon(c.polygon) for c in cells]
        self._zone_tree = STRtree(self._zone_polys) if zones else None
        self._cell_tree = STRtree(self._cell_polys) if cells else None

    def _hits(self, tree: STRtree | None, polys: list[Polygon], p: Point) -> list[int]:
        if tree is None:
            return []
        return [int(i) for i in tree.query(p) if polys[int(i)].buffer(1e-9).contains(p)]

    def locate(self, x: float, y: float) -> Location:
        p = Point(x, y)
        cell_hits = [self._cells[i] for i in self._hits(self._cell_tree, self._cell_polys, p)]
        cell = None
        if cell_hits:
            # From above only the top visible level is observable (ФТ-ЛОК-06).
            cell = max(cell_hits, key=lambda c: c.level or 0)
        zone_id = cell.zone_id if cell and cell.zone_id is not None else None
        if zone_id is None:
            zone_hits = self._hits(self._zone_tree, self._zone_polys, p)
            zone_id = self._zones[zone_hits[0]].id if zone_hits else None
        return Location(zone_id=zone_id, cell_id=cell.id if cell else None)
