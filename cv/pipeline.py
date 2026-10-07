"""Конвейер обработки одного кадра (ТЗ 4.4.5, шаги 2–8) без записи в БД."""

import time
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
from shapely.geometry import Point, Polygon

from app.services.geo import AreaRef, Locator, anchor_point, pixel_to_world
from cv.camera_model import CameraModel
from cv.detector import Detection, Detector
from cv.quality import QualityReport, QualityThresholds, assess

# Typical object heights above the support surface (м); in production from objects.size_h
NOMINAL_HEIGHT = {"box": 0.035, "container": 0.025, "pallet": 0.03}


@dataclass(frozen=True)
class Surface:
    """Horizontal support surface objects can stand on (shelf top level)."""

    polygon: list[list[float]]
    z: float


class Mapper(Protocol):
    def to_world(self, det: Detection) -> tuple[float, float]: ...


class FloorHomographyMapper:
    """ФТ-ЛОК-02 as written: one image->floor homography for every object."""

    def __init__(self, homography: list[list[float]], view: str = "top"):
        self.h = homography
        self.view = view

    def to_world(self, det: Detection) -> tuple[float, float]:
        pt = anchor_point(det.cx, det.cy, det.w, det.h, self.view)
        x, y = pixel_to_world(self.h, [pt])[0]
        return x, y


class SurfaceAwareMapper:
    """Full camera model: intersect the viewing ray with the surface the object stands on.

    Candidate planes are tried from the highest down; the first one whose intersection lands on
    that surface wins (from above, a higher object hides whatever is below it).
    """

    def __init__(self, camera: CameraModel, surfaces: list[Surface],
                 heights: dict[str, float] | None = None):
        self.camera = camera
        self.surfaces = sorted(surfaces, key=lambda s: -s.z)
        self._polys = [Polygon(s.polygon).buffer(0.01) for s in self.surfaces]
        self.heights = heights or NOMINAL_HEIGHT

    def to_world(self, det: Detection) -> tuple[float, float]:
        uv = np.array([[det.cx, det.cy]])
        h = self.heights.get(det.cls, 0.0)
        for surface, poly in zip(self.surfaces, self._polys, strict=True):
            x, y = self.camera.pixel_to_plane(uv, surface.z + h)[0]
            if poly.contains(Point(x, y)):
                return float(x), float(y)
        x, y = self.camera.pixel_to_plane(uv, h)[0]
        return float(x), float(y)


@dataclass
class LocatedDetection:
    det: Detection
    x_m: float | None = None
    y_m: float | None = None
    zone_id: int | None = None
    cell_id: int | None = None


@dataclass
class FrameResult:
    quality: QualityReport
    detections: list[LocatedDetection] = field(default_factory=list)
    below_threshold: list[Detection] = field(default_factory=list)
    people: list[Detection] = field(default_factory=list)
    rejected: str | None = None
    timings_ms: dict[str, float] = field(default_factory=dict)


@dataclass
class PipelineConfig:
    confidence: float = 0.5  # ФТ-CV-05
    tracked: tuple[str, ...] = ("box", "pallet", "container")
    max_person_ratio: float = 0.2  # ФТ-СКН-07: share of the frame covered by people
    quality: QualityThresholds = field(default_factory=QualityThresholds)


def process_frame(image: np.ndarray, detector: Detector, mapper: Mapper, locator: Locator,
                  cfg: PipelineConfig | None = None) -> FrameResult:
    cfg = cfg or PipelineConfig()
    t0 = time.perf_counter()
    q = assess(image, cfg.quality)
    t1 = time.perf_counter()
    result = FrameResult(quality=q, timings_ms={"quality": (t1 - t0) * 1000})
    if not q.ok:
        result.rejected = q.reason
        return result

    dets = detector.predict(image)
    t2 = time.perf_counter()
    result.timings_ms["detect"] = (t2 - t1) * 1000

    frame_area = image.shape[0] * image.shape[1]
    result.people = [d for d in dets if d.cls == "person" and d.confidence >= cfg.confidence]
    person_ratio = sum(d.w * d.h for d in result.people) / frame_area
    if person_ratio > cfg.max_person_ratio:
        result.rejected = f"Человек перекрывает {person_ratio:.0%} кадра"
        return result

    for d in dets:
        if d.cls not in cfg.tracked:
            continue
        if d.confidence < cfg.confidence:
            result.below_threshold.append(d)
            continue
        x, y = mapper.to_world(d)
        loc = locator.locate(x, y)
        result.detections.append(LocatedDetection(d, x, y, loc.zone_id, loc.cell_id))
    result.timings_ms["locate"] = (time.perf_counter() - t2) * 1000
    return result


def stand_locator(cells: list, zones: list[dict]) -> tuple[Locator, dict[int, str], dict[int, str]]:
    """Locator over a simulated stand; returns id->address and id->zone code maps."""
    zone_refs = [AreaRef(i, z["polygon"]) for i, z in enumerate(zones)]
    zone_ids = {z["code"]: i for i, z in enumerate(zones)}
    cell_refs = [AreaRef(1000 + i, c.polygon, level=1, zone_id=zone_ids[c.zone])
                 for i, c in enumerate(cells)]
    return (Locator(zone_refs, cell_refs),
            {1000 + i: c.address for i, c in enumerate(cells)},
            {i: z["code"] for i, z in enumerate(zones)})
