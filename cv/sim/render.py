"""Рендер синтетического монохромного кадра стенда через модель камеры."""

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from cv.camera_model import CameraModel
from cv.sim.scene import CLASS_INDEX, Scene, SceneObject, Stand

LIGHTING = {
    # base gain, gradient, light azimuth (deg), shadow length per metre of height, shadow strength
    "even": (1.0, 0.06, 30, 0.25, 0.18),
    "dim": (0.55, 0.08, 120, 0.3, 0.15),
    "side": (0.95, 0.30, 200, 0.9, 0.35),
    "bright": (1.22, 0.05, 300, 0.2, 0.15),
}


@dataclass
class RenderConfig:
    lighting: str = "even"
    noise_sigma: float = 2.5  # at full resolution, in grey levels
    blur_sigma_px: float = 0.8  # defocus at full resolution
    vignette: float = 0.12


@dataclass
class GroundTruth:
    cls: str
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels of the rendered image
    obj: SceneObject | None = None


@dataclass
class Rendered:
    image: np.ndarray
    truths: list[GroundTruth] = field(default_factory=list)

    def yolo_labels(self) -> list[str]:
        h, w = self.image.shape[:2]
        lines = []
        for t in self.truths:
            x1, y1, x2, y2 = t.bbox
            lines.append(f"{CLASS_INDEX[t.cls]} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} "
                         f"{(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
        return lines


class _Canvas:
    def __init__(self, cam: CameraModel):
        self.cam = cam
        self.img = np.zeros((cam.height, cam.width), np.float32)

    def poly(self, pts_w: np.ndarray) -> np.ndarray:
        return np.round(self.cam.project(pts_w) * 16).astype(np.int32)

    def fill(self, pts_w: np.ndarray, value: float, target: np.ndarray | None = None) -> None:
        cv2.fillPoly(self.img if target is None else target, [self.poly(pts_w)], float(value),
                     lineType=cv2.LINE_AA, shift=4)

    def outline(self, pts_w: np.ndarray, value: float, thickness: int = 1) -> None:
        cv2.polylines(self.img, [self.poly(pts_w)], True, float(value), thickness,
                      lineType=cv2.LINE_AA, shift=4)

    def px_per_m(self, z: float = 0.0) -> float:
        return 1000.0 / self.cam.mm_per_px(z)


def _rect_w(x0, y0, x1, y1, z=0.0) -> np.ndarray:
    return np.array([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]], dtype=np.float64)


def _local_rect(o: SceneObject, fx0, fy0, fx1, fy1, z) -> np.ndarray:
    """Rectangle in object-local fractions (-0.5..0.5) of length/width, at height z."""
    length, width = o.size[0], o.size[1]
    a = math.radians(o.yaw_deg)
    c, s = math.cos(a), math.sin(a)
    pts = []
    for fx, fy in [(fx0, fy0), (fx1, fy0), (fx1, fy1), (fx0, fy1)]:
        lx, ly = fx * length, fy * width
        pts.append([o.x + lx * c - ly * s, o.y + lx * s + ly * c, z])
    return np.array(pts)


def _smooth_noise(rng, h, w, cell, amp) -> np.ndarray:
    small = rng.normal(0, 1, (max(2, h // cell), max(2, w // cell))).astype(np.float32)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC) * amp


def _cuboid(cv: _Canvas, corners: np.ndarray, top_value: float, side_factor: float) -> None:
    bottom, top = corners[:4], corners[4:]
    for i in range(4):
        j = (i + 1) % 4
        face = np.array([bottom[i], bottom[j], top[j], top[i]])
        cv.fill(face, top_value * side_factor * (0.85 + 0.1 * (i % 2)))
    cv.fill(top, top_value)
    cv.outline(top, top_value * 0.6)


def _draw_object(cv: _Canvas, o: SceneObject, rng: np.random.Generator) -> None:
    z0, h = o.z, o.size[2]
    if o.cls == "box":
        v = 255 * o.shade
        _cuboid(cv, o.corners(), v, 0.62)
        top = z0 + h
        cv.fill(_local_rect(o, -0.5, -0.08, 0.5, 0.08, top), min(255, v * 1.12))  # tape
        if o.has_label:
            lab = _local_rect(o, 0.1, -0.42, 0.42, -0.12, top)
            cv.fill(lab, 235)
            for _ in range(10):  # QR-like modules
                fx, fy = rng.uniform(0.12, 0.38), rng.uniform(-0.4, -0.16)
                cv.fill(_local_rect(o, fx, fy, fx + 0.04, fy + 0.05, top), 30)
    elif o.cls == "container":
        v = 255 * o.shade * 0.55
        _cuboid(cv, o.corners(), v, 0.75)
        top = z0 + h
        cv.fill(_local_rect(o, -0.42, -0.38, 0.42, 0.38, top), v * 0.6)  # open interior
        for fx in (-0.25, 0.0, 0.25):
            cv.fill(_local_rect(o, fx - 0.015, -0.38, fx + 0.015, 0.38, top), v * 0.8)
    elif o.cls == "pallet":
        deck = z0 + h
        base = 255 * (0.55 + 0.25 * o.shade)
        corners = o.corners().copy()
        corners[4:, 2] = deck
        _cuboid(cv, corners, base * 0.55, 0.7)  # gaps between planks are dark
        for fy in (-0.5, -0.2, 0.1, 0.38):
            cv.fill(_local_rect(o, -0.5, fy, 0.5, fy + 0.12, deck), base)
        if o.loaded:
            cargo = SceneObject("box", o.x, o.y, deck, (o.size[0] * 0.85, o.size[1] * 0.85, 0.03),
                                o.yaw_deg, None, None, shade=o.shade)
            _cuboid(cv, cargo.corners(), 255 * (0.5 + 0.3 * o.shade), 0.62)


def _draw_shelf(cv: _Canvas, shelf: dict, top_z: float) -> None:
    x, y, w, d = shelf["x"], shelf["y"], shelf["width"], shelf["depth"]
    cv.fill(_rect_w(x - w / 2, y - d / 2, x + w / 2, y + d / 2, top_z), 178)
    cv.outline(_rect_w(x - w / 2, y - d / 2, x + w / 2, y + d / 2, top_z), 95, 2)


def _draw_posts(cv: _Canvas, shelf: dict, z_from: float, z_to: float) -> None:
    x, y, w, d = shelf["x"], shelf["y"], shelf["width"], shelf["depth"]
    p = 0.008
    for sx in (-1, 1):
        for sy in (-1, 1):
            px, py = x + sx * (w / 2 - p / 2), y + sy * (d / 2 - p / 2)
            post = SceneObject("rack", px, py, z_from, (p, p, z_to - z_from), 0.0, None, None)
            _cuboid(cv, post.corners(), 55, 0.8)


def _person(cv: _Canvas, stand: Stand, p: dict, draw: bool = True) -> tuple[np.ndarray, float]:
    """Arm entering from a table edge at height p['z']; returns its image polygon."""
    L, W, z = stand.length, stand.width, p["z"]
    edge, pos, reach = p["edge"], p["pos"], p["reach"]
    if edge == "left":
        start, direction = (-0.15, pos * W), (1, 0)
    elif edge == "right":
        start, direction = (L + 0.15, pos * W), (-1, 0)
    elif edge == "bottom":
        start, direction = (pos * L, -0.15), (0, 1)
    else:
        start, direction = (pos * L, W + 0.15), (0, -1)
    end = (start[0] + direction[0] * (reach + 0.15), start[1] + direction[1] * (reach + 0.15))
    half = 0.04
    nx, ny = -direction[1] * half, direction[0] * half
    arm = np.array([[start[0] + nx, start[1] + ny, z], [end[0] + nx, end[1] + ny, z],
                    [end[0] - nx, end[1] - ny, z], [start[0] - nx, start[1] - ny, z]])
    hand_c = cv.cam.project(np.array([[end[0], end[1], z]]))[0]
    r = 0.05 * cv.px_per_m(z)
    if draw:
        cv.fill(arm, 120)  # sleeve
        cv2.ellipse(cv.img, (int(hand_c[0]), int(hand_c[1])), (int(r), int(r * 0.8)), 0, 0,
                    360, 185, -1, cv2.LINE_AA)
    poly = np.vstack([cv.cam.project(arm), [[hand_c[0] - r, hand_c[1] - r],
                                            [hand_c[0] + r, hand_c[1] + r]]])
    return poly, r


def _bbox(uv: np.ndarray, w: int, h: int) -> tuple[float, float, float, float, float]:
    x1, y1 = uv.min(axis=0)
    x2, y2 = uv.max(axis=0)
    full = max(1e-9, (x2 - x1) * (y2 - y1))
    cx1, cy1, cx2, cy2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
    visible = max(0, cx2 - cx1) * max(0, cy2 - cy1) / full
    return cx1, cy1, cx2, cy2, visible


def _overlap(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = max(1e-9, (a[2] - a[0]) * (a[3] - a[1]))
    return ix * iy / area


def render(stand: Stand, scene: Scene, camera: CameraModel, rng: np.random.Generator,
           cfg: RenderConfig | None = None, scale: float = 1.0,
           draw_markers: bool = True) -> Rendered:
    cfg = cfg or RenderConfig()
    cam = camera.scaled(scale) if scale != 1.0 else camera
    cv = _Canvas(cam)
    H, W = cv.img.shape
    L, Wd = stand.length, stand.width
    gain, grad, az, shadow_len, shadow_k = LIGHTING[cfg.lighting]

    # Floor around the table, then the table top with wood-like texture.
    cv.img[:] = 45 + _smooth_noise(rng, H, W, 64, 6)
    table_mask = np.zeros_like(cv.img)
    cv.fill(_rect_w(-0.01, -0.01, L + 0.01, Wd + 0.01), 1.0, table_mask)
    xs = np.linspace(0, 1, W, dtype=np.float32)
    grain = (np.sin(xs * 260 + _smooth_noise(rng, H, W, 48, 2.5)) * 5).astype(np.float32)
    table = 150 + _smooth_noise(rng, H, W, 96, 9) + grain
    cv.img = cv.img * (1 - table_mask) + table * table_mask

    tape = 0.004
    for z in stand.spec["zones"]:
        poly = np.array([[x, y, 0.0] for x, y in z["polygon"]])
        cv.outline(poly, 70, max(1, int(tape * cv.px_per_m())))
    for c in stand.cells:
        if c.shelf is None:
            poly = np.array([[x, y, 0.0] for x, y in c.polygon])
            cv.outline(poly, 105, max(1, int(0.0025 * cv.px_per_m())))

    if draw_markers:
        for mx, my in stand.spec["markers"]:
            cv.fill(_rect_w(mx - 0.015, my - 0.015, mx + 0.015, my + 0.015), 235)
            cv.fill(_rect_w(mx - 0.012, my - 0.0015, mx + 0.012, my + 0.0015), 20)
            cv.fill(_rect_w(mx - 0.0015, my - 0.012, mx + 0.0015, my + 0.012), 20)

    for d in scene.distractors:
        if d["kind"] == "roll":
            c = cam.project(np.array([[d["x"], d["y"], 0.02]]))[0]
            r = 0.025 * cv.px_per_m(0.02)
            cv2.circle(cv.img, (int(c[0]), int(c[1])), int(r), 60, max(2, int(r * 0.35)),
                       cv2.LINE_AA)
        else:
            o = SceneObject("x", d["x"], d["y"], 0.0,
                            (0.12, 0.008, 0.008) if d["kind"] == "pen" else (0.1, 0.07, 0.0005),
                            d["yaw"], None, None)
            cv.fill(o.corners()[4:], 40 if d["kind"] == "pen" else 225)

    shelves_top = {s["code"]: stand.shelf_top_z(s) for s in stand.spec["shelves"]}
    for s in stand.spec["shelves"]:
        _draw_posts(cv, s, 0.0, shelves_top[s["code"]])
        _draw_shelf(cv, s, shelves_top[s["code"]])

    # Soft shadows cast by objects onto the surface they stand on.
    shadow = np.zeros((H // 4, W // 4), np.float32)
    small_cam = cam.scaled(0.25)
    dx, dy = math.cos(math.radians(az)) * shadow_len, math.sin(math.radians(az)) * shadow_len
    for o in scene.objects:
        foot = o.corners()[:4].copy()
        hgt = o.top_z - o.z
        foot[:, 0] += dx * hgt
        foot[:, 1] += dy * hgt
        ring = np.vstack([o.corners()[:4], foot])
        hull = cv2.convexHull(small_cam.project(ring).astype(np.float32))
        cv2.fillPoly(shadow, [hull.astype(np.int32)], 1.0)
    shadow = cv2.GaussianBlur(shadow, (0, 0), max(1.0, 0.004 * cv.px_per_m() / 4))
    cv.img *= 1 - shadow_k * cv2.resize(shadow, (W, H))

    # Person first so occluded objects can be removed from the ground truth.
    person_poly = None
    objects = list(scene.objects)
    if scene.person:
        person_poly, _ = _person(cv, stand, scene.person, draw=False)
        pb = _bbox(person_poly, W, H)[:4]
        objects = [o for o in objects if _overlap(_bbox(cam.project(o.corners()), W, H)[:4],
                                                  pb) < 0.3]

    truths: list[GroundTruth] = []
    for o in sorted(objects, key=lambda o: o.top_z):
        _draw_object(cv, o, rng)
        x1, y1, x2, y2, vis = _bbox(cam.project(o.corners()), W, H)
        if vis >= 0.5:
            truths.append(GroundTruth(o.cls, (x1, y1, x2, y2), o))

    for s in stand.spec["shelves"]:
        _draw_posts(cv, s, shelves_top[s["code"]], s["height"])

    if scene.person:
        poly, _ = _person(cv, stand, scene.person)
        x1, y1, x2, y2, vis = _bbox(poly, W, H)
        if vis > 0 and (x2 - x1) * (y2 - y1) > 0:
            truths.append(GroundTruth("person", (x1, y1, x2, y2)))

    # Optics and sensor: illumination field, vignetting, defocus, noise, 8-bit quantisation.
    nx = (np.arange(W, dtype=np.float32) / W - 0.5)[None, :]
    ny = (np.arange(H, dtype=np.float32) / H - 0.5)[:, None]
    a = math.radians(az)
    img = cv.img
    img *= gain * (1 + grad * 2 * (nx * math.cos(a) + ny * math.sin(a)))
    img *= 1 - cfg.vignette * 2 * (nx**2 + ny**2)
    blur = cfg.blur_sigma_px * scale
    if blur > 0.3:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    noise = rng.standard_normal(img.shape, dtype=np.float32)
    noise *= cfg.noise_sigma * max(scale, 0.25)
    img += noise
    image = np.clip(img, 0, 255, out=img).astype(np.uint8)
    return Rendered(image, truths)
