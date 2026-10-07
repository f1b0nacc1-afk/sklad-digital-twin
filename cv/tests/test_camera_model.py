import numpy as np
import pytest

from cv.camera_model import CameraModel, nominal_intrinsics


def test_nominal_optics_match_tz():
    cam = CameraModel.looking_down(0.6, 0.4, 1.0)
    fp = cam.floor_footprint()
    width, height = np.ptp(fp[:, 0]), np.ptp(fp[:, 1])
    assert width == pytest.approx(1.094, abs=0.002)  # ТЗ 4.4.1: 1,09 × 0,73 м at 1 m
    assert height == pytest.approx(0.73, abs=0.002)
    assert cam.mm_per_px() == pytest.approx(0.2, abs=1e-6)


def test_image_orientation_matches_plan():
    cam = CameraModel.looking_down(0.6, 0.4, 1.15)
    centre = cam.project(np.array([[0.6, 0.4, 0.0]]))[0]
    assert centre == pytest.approx([2736, 1824], abs=1e-6)
    right, up = cam.project(np.array([[0.7, 0.4, 0.0], [0.6, 0.5, 0.0]]))
    assert right[0] > centre[0]  # +X -> right
    assert up[1] < centre[1]  # +Y -> up in the image


def test_project_and_back_project_roundtrip():
    cam = CameraModel.looking_down(0.6, 0.4, 1.15, tilt_x_deg=1.5, tilt_y_deg=-1, yaw_deg=3)
    pts = np.array([[0.1, 0.1, 0.0], [1.0, 0.7, 0.133], [0.5, 0.3, 0.05]])
    uv = cam.project(pts)
    back = cam.pixel_to_plane(uv, pts[:, 2])
    np.testing.assert_allclose(back, pts[:, :2], atol=1e-9)


def test_pose_from_markers_recovers_camera():
    true = CameraModel.looking_down(0.61, 0.39, 1.16, tilt_x_deg=1.2, yaw_deg=-2)
    markers = np.array([[0.04, 0.04, 0], [1.16, 0.04, 0], [1.16, 0.76, 0], [0.04, 0.76, 0],
                        [0.6, 0.4, 0], [0.86, 0.4, 0]], dtype=float)
    est = CameraModel.from_markers(markers, true.project(markers), true.K)
    np.testing.assert_allclose(est.centre, true.centre, atol=1e-6)
    probe = np.array([[0.3, 0.6, 0.133]])
    np.testing.assert_allclose(est.pixel_to_plane(true.project(probe), 0.133), probe[:, :2],
                               atol=1e-6)


def test_parallax_of_raised_point_under_floor_assumption():
    """A point 13 cm above the floor, 40 cm off-axis, is misplaced by ~5 cm on the floor plane."""
    cam = CameraModel.looking_down(0.6, 0.4, 1.15)
    uv = cam.project(np.array([[1.0, 0.4, 0.133]]))
    x_floor = cam.pixel_to_plane(uv, 0.0)[0, 0]
    assert x_floor - 1.0 == pytest.approx(0.4 * 0.133 / (1.15 - 0.133), rel=1e-6)


def test_scaled_camera():
    cam = CameraModel.looking_down(0.6, 0.4, 1.15).scaled(0.25)
    assert (cam.width, cam.height) == (1368, 912)
    assert cam.K[0, 0] == pytest.approx(nominal_intrinsics()[0, 0] / 4)


def test_dict_roundtrip():
    cam = CameraModel.looking_down(0.6, 0.4, 1.15, yaw_deg=2)
    np.testing.assert_allclose(CameraModel.from_dict(cam.to_dict()).R, cam.R)
