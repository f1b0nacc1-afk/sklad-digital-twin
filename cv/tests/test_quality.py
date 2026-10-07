import numpy as np

from cv.quality import assess, to_mono8


def textured(h=600, w=900, seed=0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((h, w), 120, np.uint8)
    for _ in range(60):
        x, y = rng.integers(0, w - 60), rng.integers(0, h - 60)
        img[y:y + 50, x:x + 50] = rng.integers(40, 200)
    return img


def test_good_frame_passes():
    report = assess(textured())
    assert report.ok, report.reason


def test_black_frame_rejected():
    report = assess(np.zeros((600, 900), np.uint8))
    assert not report.ok and "тёмный" in report.reason


def test_overexposed_frame_rejected():
    img = textured()
    img[:, :200] = 255
    report = assess(img)
    assert not report.ok and "Пересвеченный" in report.reason


def test_blurred_frame_rejected():
    import cv2

    blurred = cv2.GaussianBlur(textured(), (0, 0), 15)
    report = assess(blurred)
    assert not report.ok and "Размытый" in report.reason


def test_empty_image_rejected():
    assert not assess(np.zeros((0, 0), np.uint8)).ok


def test_mono12_conversion():
    img = np.array([[0, 4095]], np.uint16)
    np.testing.assert_array_equal(to_mono8(img), [[0, 255]])


def test_bgr_conversion():
    img = np.zeros((2, 2, 3), np.uint8)
    assert to_mono8(img).shape == (2, 2)
