"""Модель камеры-обскуры: внутренние параметры + поза относительно склада.

Система координат склада: X вдоль длины, Y вдоль ширины, Z вверх (м).
Изображение: u вправо, v вниз (пиксели).
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

# Имеющаяся оптика (ТЗ 4.4.1): IMX183, пиксель 2,4 мкм, 5472×3648; Computar 12 мм
SENSOR_W_PX, SENSOR_H_PX = 5472, 3648
PIXEL_MM = 0.0024
FOCAL_MM = 12.0


def nominal_intrinsics(
    focal_mm: float = FOCAL_MM, pixel_mm: float = PIXEL_MM,
    width: int = SENSOR_W_PX, height: int = SENSOR_H_PX,
) -> np.ndarray:
    f = focal_mm / pixel_mm
    return np.array([[f, 0, width / 2], [0, f, height / 2], [0, 0, 1]], dtype=np.float64)


def _rot(axis: str, deg: float) -> np.ndarray:
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


# Camera looking straight down: image right = +X, image down = -Y, optical axis = -Z.
_DOWN = np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]], dtype=np.float64)


@dataclass
class CameraModel:
    K: np.ndarray
    R: np.ndarray  # world -> camera rotation
    t: np.ndarray  # world -> camera translation, shape (3,)
    dist: np.ndarray = field(default_factory=lambda: np.zeros(5))
    width: int = SENSOR_W_PX
    height: int = SENSOR_H_PX

    @classmethod
    def looking_down(
        cls, x: float, y: float, height_m: float, *, tilt_x_deg: float = 0.0,
        tilt_y_deg: float = 0.0, yaw_deg: float = 0.0, K: np.ndarray | None = None,
    ) -> "CameraModel":
        """Camera above (x, y) at height_m with small mounting errors."""
        R = _rot("x", tilt_x_deg) @ _rot("y", tilt_y_deg) @ _rot("z", yaw_deg) @ _DOWN
        centre = np.array([x, y, height_m], dtype=np.float64)
        return cls(K=nominal_intrinsics() if K is None else K, R=R, t=-R @ centre)

    @property
    def centre(self) -> np.ndarray:
        return -self.R.T @ self.t

    def scaled(self, s: float) -> "CameraModel":
        """Same camera with the image resampled by factor s (for fast rendering)."""
        K = self.K.copy()
        K[:2] *= s
        return CameraModel(K, self.R, self.t, self.dist, round(self.width * s),
                           round(self.height * s))

    def project(self, points_w: np.ndarray) -> np.ndarray:
        pts = np.asarray(points_w, dtype=np.float64).reshape(-1, 3)
        rvec, _ = cv2.Rodrigues(self.R)
        uv, _ = cv2.projectPoints(pts, rvec, self.t, self.K, self.dist)
        return uv.reshape(-1, 2)

    def pixel_to_plane(self, uv: np.ndarray, z: float | np.ndarray = 0.0) -> np.ndarray:
        """Back-project pixels onto horizontal plane(s) Z = z. Returns (N, 2) world XY."""
        uv = np.asarray(uv, dtype=np.float64).reshape(-1, 1, 2)
        norm = cv2.undistortPoints(uv, self.K, self.dist).reshape(-1, 2)
        rays_cam = np.column_stack([norm, np.ones(len(norm))])
        rays_w = rays_cam @ self.R  # == (R.T @ ray.T).T
        c = self.centre
        s = (np.broadcast_to(z, len(rays_w)) - c[2]) / rays_w[:, 2]
        return (c[:2] + rays_w[:, :2] * s[:, None])

    def floor_footprint(self) -> np.ndarray:
        """World XY of the four image corners on the floor (field of view, ФТ-КАМ-06)."""
        corners = [[0, 0], [self.width, 0], [self.width, self.height], [0, self.height]]
        return self.pixel_to_plane(np.array(corners, dtype=np.float64), 0.0)

    def mm_per_px(self, z: float = 0.0) -> float:
        return float((self.centre[2] - z) / self.K[0, 0] * 1000)

    @classmethod
    def from_markers(
        cls, world_xyz: np.ndarray, image_uv: np.ndarray, K: np.ndarray,
        dist: np.ndarray | None = None, width: int = SENSOR_W_PX, height: int = SENSOR_H_PX,
    ) -> "CameraModel":
        """Recover camera pose from >= 4 reference markers with known coordinates (solvePnP)."""
        world_xyz = np.asarray(world_xyz, dtype=np.float64).reshape(-1, 3)
        image_uv = np.asarray(image_uv, dtype=np.float64).reshape(-1, 2)
        if len(world_xyz) < 4:
            raise ValueError("at least 4 markers are required")
        dist = np.zeros(5) if dist is None else np.asarray(dist, dtype=np.float64)
        ok, rvec, tvec = cv2.solvePnP(world_xyz, image_uv, K, dist, flags=cv2.SOLVEPNP_IPPE)
        if not ok:
            raise ValueError("solvePnP failed")
        rvec, tvec = cv2.solvePnPRefineLM(world_xyz, image_uv, K, dist, rvec, tvec)
        R, _ = cv2.Rodrigues(rvec)
        return cls(K=K, R=R, t=tvec.reshape(3), dist=dist, width=width, height=height)

    def to_dict(self) -> dict:
        return {"K": self.K.tolist(), "R": self.R.tolist(), "t": self.t.tolist(),
                "dist": self.dist.tolist(), "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, d: dict) -> "CameraModel":
        return cls(np.array(d["K"]), np.array(d["R"]), np.array(d["t"]), np.array(d["dist"]),
                   d["width"], d["height"])
