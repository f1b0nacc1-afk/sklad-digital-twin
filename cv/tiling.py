"""Тайлинг кадра высокого разрешения и объединение результатов (ФТ-CV-03)."""

import math

import numpy as np


def tile_grid(
    width: int, height: int, tile: int, overlap: float
) -> list[tuple[int, int, int, int]]:
    """Evenly spaced tiles (x0, y0, x1, y1) with at least `overlap`; no padding at the edges."""
    if not 0 <= overlap < 1:
        raise ValueError("overlap must be in [0, 1)")
    step = tile * (1 - overlap)

    def starts(size: int) -> list[int]:
        if size <= tile:
            return [0]
        n = math.ceil((size - tile) / step) + 1
        return [round(i * (size - tile) / (n - 1)) for i in range(n)]

    return [(x, y, min(x + tile, width), min(y + tile, height))
            for y in starts(height) for x in starts(width)]


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU between (N,4) and (M,4) boxes in x1y1x2y2."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / np.maximum(area_a[:, None] + area_b[None, :] - inter, 1e-9)


def nms(dets: np.ndarray, iou_thr: float = 0.5) -> np.ndarray:
    """Class-wise NMS over (N,6) rows [x1, y1, x2, y2, score, cls]."""
    if len(dets) == 0:
        return dets.reshape(0, 6)
    keep_all = []
    for c in np.unique(dets[:, 5]):
        d = dets[dets[:, 5] == c]
        d = d[np.argsort(-d[:, 4])]
        while len(d):
            keep_all.append(d[0])
            if len(d) == 1:
                break
            ious = iou_matrix(d[:1, :4], d[1:, :4])[0]
            d = d[1:][ious < iou_thr]
    return np.array(keep_all).reshape(-1, 6)


def drop_cut_boxes(dets: np.ndarray, tile_box: tuple[int, int, int, int], image_w: int,
                   image_h: int, margin: int = 2) -> np.ndarray:
    """Drop boxes touching an inner tile border: the neighbour tile sees the whole object."""
    if len(dets) == 0:
        return dets
    x0, y0, x1, y1 = tile_box
    cut = np.zeros(len(dets), bool)
    if x0 > 0:
        cut |= dets[:, 0] <= x0 + margin
    if y0 > 0:
        cut |= dets[:, 1] <= y0 + margin
    if x1 < image_w:
        cut |= dets[:, 2] >= x1 - margin
    if y1 < image_h:
        cut |= dets[:, 3] >= y1 - margin
    return dets[~cut]
