"""Детектор объектов (ПС-2): Mono→3ch, масштаб, тайлинг, YOLO, NMS (ФТ-CV-01…05)."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from cv.quality import to_mono8
from cv.tiling import drop_cut_boxes, nms, tile_grid

# Model output rows: [x1, y1, x2, y2, score, class_index] in pixels of the given image
PredictBatch = Callable[[list[np.ndarray]], list[np.ndarray]]


@dataclass(frozen=True)
class Detection:
    cls: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def w(self) -> float:
        return self.x2 - self.x1

    @property
    def h(self) -> float:
        return self.y2 - self.y1

    @property
    def xyxy(self) -> tuple[float, float, float, float]:
        return self.x1, self.y1, self.x2, self.y2


def prepare(image: np.ndarray, scale: float) -> np.ndarray:
    """Mono8/Mono12/BGR -> 3 identical channels at working scale (ФТ-CV-04)."""
    mono = to_mono8(image)
    if scale != 1.0:
        mono = cv2.resize(mono, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(mono, cv2.COLOR_GRAY2BGR)


@dataclass
class DetectorConfig:
    classes: tuple[str, ...] = ("box", "pallet", "container", "person")
    scale: float = 0.25  # 5472x3648 -> 1368x912: a 3 cm box is still >= 30 px
    tile: int | None = None  # None: whole working image in one pass
    overlap: float = 0.2
    iou: float = 0.5
    min_confidence: float = 0.05  # keep low-confidence detections for analysis (ФТ-CV-05)


class Detector:
    """Model-agnostic part: scaling, tiling, merging. The model is a batch predict function."""

    def __init__(self, predict_batch: PredictBatch, config: DetectorConfig | None = None,
                 version: str = "unknown"):
        self.predict_batch = predict_batch
        self.config = config or DetectorConfig()
        self.version = version

    def predict(self, image: np.ndarray) -> list[Detection]:
        cfg = self.config
        work = prepare(image, cfg.scale)
        h, w = work.shape[:2]
        if cfg.tile and (w > cfg.tile or h > cfg.tile):
            boxes = tile_grid(w, h, cfg.tile, cfg.overlap)
            outputs = self.predict_batch([work[y0:y1, x0:x1] for x0, y0, x1, y1 in boxes])
            parts = []
            for (x0, y0, x1, y1), out in zip(boxes, outputs, strict=True):
                out = np.asarray(out, dtype=np.float64).reshape(-1, 6).copy()
                out[:, [0, 2]] += x0
                out[:, [1, 3]] += y0
                parts.append(drop_cut_boxes(out, (x0, y0, x1, y1), w, h))
            dets = nms(np.vstack(parts) if parts else np.zeros((0, 6)), cfg.iou)
        else:
            dets = np.asarray(self.predict_batch([work])[0], dtype=np.float64).reshape(-1, 6)
        dets = dets[dets[:, 4] >= cfg.min_confidence]
        inv = 1.0 / cfg.scale
        return [
            Detection(cfg.classes[int(c)], float(s), x1 * inv, y1 * inv, x2 * inv, y2 * inv)
            for x1, y1, x2, y2, s, c in dets
            if int(c) < len(cfg.classes)
        ]


def yolo_detector(weights: str | Path, config: DetectorConfig | None = None,
                  imgsz: int = 1376, device: str | None = None) -> Detector:
    """Ultralytics YOLO backend (uv sync --extra ml)."""
    from ultralytics import YOLO

    model = YOLO(str(weights))
    cfg = config or DetectorConfig()

    def predict_batch(images: list[np.ndarray]) -> list[np.ndarray]:
        results = model.predict(images, imgsz=imgsz, conf=cfg.min_confidence, iou=cfg.iou,
                                device=device, verbose=False)
        return [np.column_stack([r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(),
                                 r.boxes.cls.cpu().numpy()]) for r in results]

    return Detector(predict_batch, cfg, version=Path(weights).stem)
