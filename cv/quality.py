"""Контроль качества кадра до распознавания (ФТ-СКН-06, ТЗ 4.4.5 п. 2)."""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class QualityThresholds:
    min_mean: float = 20.0
    max_mean: float = 235.0
    max_overexposed_ratio: float = 0.05
    overexposed_level: int = 250
    min_laplacian_var: float = 100.0
    # Laplacian is computed on a downscaled copy: 20 MP is slow and noise inflates variance.
    analysis_width: int = 1600


@dataclass(frozen=True)
class QualityReport:
    ok: bool
    reason: str | None
    mean: float
    overexposed_ratio: float
    laplacian_var: float


def to_mono8(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if image.dtype == np.uint16:
        # Mono12 packed into uint16 occupies the low 12 bits.
        max_val = 4095 if image.max() <= 4095 else 65535
        image = (image.astype(np.float32) * (255.0 / max_val)).round().astype(np.uint8)
    return image


def assess(image: np.ndarray, t: QualityThresholds | None = None) -> QualityReport:
    t = t or QualityThresholds()
    mono = to_mono8(image)
    if mono.size == 0:
        return QualityReport(False, "Пустое изображение", 0.0, 0.0, 0.0)

    if mono.shape[1] > t.analysis_width:
        scale = t.analysis_width / mono.shape[1]
        small = cv2.resize(mono, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        small = mono

    mean = float(small.mean())
    over = float((small >= t.overexposed_level).mean())
    lap = float(cv2.Laplacian(small, cv2.CV_64F).var())

    reason = None
    if mean < t.min_mean:
        reason = f"Слишком тёмный кадр (средняя яркость {mean:.0f})"
    elif mean > t.max_mean or over > t.max_overexposed_ratio:
        reason = f"Пересвеченный кадр (пересвет {over:.0%})"
    elif lap < t.min_laplacian_var:
        reason = f"Размытый кадр (дисперсия лапласиана {lap:.0f})"
    return QualityReport(reason is None, reason, mean, over, lap)
