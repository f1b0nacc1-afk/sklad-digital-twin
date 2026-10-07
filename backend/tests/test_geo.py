import numpy as np
import pytest

from app.services.geo import (
    AreaRef,
    Locator,
    anchor_point,
    compute_homography,
    pixel_to_world,
    undistort_points,
)

# Macet: 5472x3648 frame covers 1.094 x 0.7296 m -> 0.2 mm/px, image y grows downward.
SCALE = 0.0002
IMG_H = 3648


def px_to_world_truth(u: float, v: float) -> list[float]:
    return [u * SCALE, (IMG_H - v) * SCALE]


CORNERS_PX = [[0, 0], [5472, 0], [5472, 3648], [0, 3648]]


def test_homography_recovers_affine_mapping_exactly():
    world = [px_to_world_truth(*p) for p in CORNERS_PX]
    result = compute_homography(CORNERS_PX, world)
    assert result.rmse_m < 1e-6
    x, y = pixel_to_world(result.matrix, [[2736, 1824]])[0]
    assert x == pytest.approx(0.5472, abs=1e-6)
    assert y == pytest.approx(0.3648, abs=1e-6)


def test_homography_handles_perspective():
    h_true = np.array([[0.001, 0.0002, 0.1], [0.0001, 0.0012, 0.2], [1e-6, 2e-6, 1.0]])
    px = [[100, 100], [5000, 150], [5300, 3500], [200, 3400], [2700, 1800]]
    world = pixel_to_world(h_true, px)
    result = compute_homography(px, world)
    probe = [[1234, 2345]]
    assert pixel_to_world(result.matrix, probe)[0] == pytest.approx(
        pixel_to_world(h_true, probe)[0], abs=1e-6
    )


def test_homography_reports_error_on_noisy_points():
    world = [px_to_world_truth(*p) for p in CORNERS_PX] + [px_to_world_truth(2736, 1824)]
    world[-1][0] += 0.01
    result = compute_homography([*CORNERS_PX, [2736, 1824]], world)
    assert 0 < result.rmse_m < 0.01
    assert len(result.per_point_error_m) == 5


def test_homography_requires_four_points():
    with pytest.raises(ValueError):
        compute_homography(CORNERS_PX[:3], [[0, 0], [1, 0], [1, 1]])


def test_undistort_with_zero_distortion_is_identity():
    k = [[2500, 0, 2736], [0, 2500, 1824], [0, 0, 1]]
    pts = [[100.0, 200.0], [5000.0, 3000.0]]
    np.testing.assert_allclose(undistort_points(pts, k, [0, 0, 0, 0, 0]), pts, atol=1e-6)


def test_anchor_point_modes():
    assert anchor_point(100, 200, 40, 60, "top") == [100, 200]
    assert anchor_point(100, 200, 40, 60, "oblique") == [100, 230]


@pytest.fixture
def locator() -> Locator:
    zones = [
        AreaRef(1, [[0, 0], [10, 0], [10, 10], [0, 10]]),
        AreaRef(2, [[10, 0], [20, 0], [20, 10], [10, 10]]),
    ]
    cell_poly = [[2, 2], [3, 2], [3, 3], [2, 3]]
    cells = [
        AreaRef(101, cell_poly, level=1, zone_id=1),
        AreaRef(102, cell_poly, level=2, zone_id=1),
        AreaRef(201, [[12, 2], [13, 2], [13, 3], [12, 3]], level=None, zone_id=2),
    ]
    return Locator(zones, cells)


def test_locate_picks_top_visible_level(locator):
    loc = locator.locate(2.5, 2.5)
    assert loc.cell_id == 102
    assert loc.zone_id == 1
    assert loc.is_addressed


def test_locate_floor_cell(locator):
    assert locator.locate(12.5, 2.5).cell_id == 201


def test_locate_outside_addressed_storage(locator):
    loc = locator.locate(5, 5)
    assert loc.cell_id is None
    assert loc.zone_id == 1
    assert not loc.is_addressed


def test_locate_outside_warehouse(locator):
    loc = locator.locate(50, 50)
    assert loc.zone_id is None and loc.cell_id is None


def test_empty_locator():
    assert Locator([], []).locate(1, 1).zone_id is None
