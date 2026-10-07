import numpy as np
import pytest

from cv.detector import Detector, DetectorConfig, prepare
from cv.tiling import drop_cut_boxes, iou_matrix, nms, tile_grid


def test_tile_grid_covers_image_without_padding():
    tiles = tile_grid(5472, 3648, 1280, 0.2)
    assert all(x1 - x0 == 1280 and y1 - y0 == 1280 for x0, y0, x1, y1 in tiles)
    assert max(t[2] for t in tiles) == 5472 and max(t[3] for t in tiles) == 3648
    assert len(tiles) == 6 * 4
    xs = sorted({t[0] for t in tiles})
    steps = np.diff(xs)
    assert steps.max() - steps.min() <= 1  # evenly spaced
    assert 1280 - steps.max() >= 0.2 * 1280  # overlap is at least 20 %


def test_tile_grid_small_image_single_tile():
    assert tile_grid(800, 600, 1280, 0.2) == [(0, 0, 800, 600)]


def test_iou():
    a = np.array([[0, 0, 10, 10]], float)
    b = np.array([[5, 0, 15, 10], [20, 20, 30, 30]], float)
    np.testing.assert_allclose(iou_matrix(a, b), [[1 / 3, 0]])


def test_nms_is_class_wise():
    d = np.array([[0, 0, 10, 10, 0.9, 0], [1, 1, 10, 10, 0.8, 0], [1, 1, 10, 10, 0.7, 1]])
    kept = nms(d, 0.5)
    assert len(kept) == 2
    assert set(kept[:, 5]) == {0, 1}


def test_drop_cut_boxes_keeps_image_border_boxes():
    d = np.array([[0, 5, 20, 20, 0.9, 0], [90, 5, 100, 20, 0.9, 0]], float)
    kept = drop_cut_boxes(d, (0, 0, 100, 100), image_w=300, image_h=100)
    assert len(kept) == 1 and kept[0, 0] == 0


def test_prepare_mono_to_three_channels():
    out = prepare(np.full((400, 600), 77, np.uint8), 0.5)
    assert out.shape == (200, 300, 3) and (out == 77).all()


def _fake_model(objects):
    """Fake predictor: 'sees' the given full-image boxes when they are fully inside the input."""

    def predict(images, offsets):
        outs = []
        for img, (ox, oy) in zip(images, offsets, strict=True):
            h, w = img.shape[:2]
            rows = [[x1 - ox, y1 - oy, x2 - ox, y2 - oy, 0.9, c] for x1, y1, x2, y2, c in objects
                    if x1 >= ox and y1 >= oy and x2 <= ox + w and y2 <= oy + h]
            outs.append(np.array(rows, float).reshape(-1, 6))
        return outs

    return predict


def test_tiled_detection_finds_each_object_once():
    # Working image 1368x912 (scale 0.25), tiles 640 with 20 % overlap
    objects = [(100, 100, 160, 150, 0), (600, 400, 700, 470, 1), (1300, 850, 1360, 905, 2)]
    tiles = tile_grid(1368, 912, 640, 0.2)
    predict = _fake_model(objects)

    def predict_batch(images):
        return predict(images, [(x0, y0) for x0, y0, _, _ in tiles])

    det = Detector(predict_batch, DetectorConfig(scale=0.25, tile=640, overlap=0.2))
    found = det.predict(np.zeros((3648, 5472), np.uint8))
    assert sorted(d.cls for d in found) == ["box", "container", "pallet"]
    pallet = next(d for d in found if d.cls == "pallet")
    assert (pallet.x1, pallet.y1, pallet.x2, pallet.y2) == pytest.approx((2400, 1600, 2800, 1880))


def test_low_confidence_filtered():
    def predict_batch(images):
        return [np.array([[0, 0, 10, 10, 0.01, 0], [0, 0, 10, 10, 0.3, 1]])]

    found = Detector(predict_batch, DetectorConfig(scale=1.0)).predict(np.zeros((20, 20), np.uint8))
    assert [d.cls for d in found] == ["pallet"]
