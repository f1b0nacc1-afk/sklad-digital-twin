"""Испытание конвейера на виртуальном стенде (аналог Т-05, Т-06, Т-08, Т-17, Т-19…Т-21).

    uv run python -m cv.sim.evaluate --weights models_store/sklad-sim-v1.pt --scenes 40
"""

import argparse
import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from app.services.geo import compute_homography, pixel_to_world
from cv.camera_model import CameraModel, nominal_intrinsics
from cv.detector import DetectorConfig, yolo_detector
from cv.pipeline import (
    FloorHomographyMapper,
    PipelineConfig,
    Surface,
    SurfaceAwareMapper,
    process_frame,
    stand_locator,
)
from cv.quality import assess
from cv.sim.dataset import RENDER_SCALE, WORK_SCALE, random_session, to_work, write_data_yaml
from cv.sim.render import LIGHTING, RenderConfig, render
from cv.sim.scene import Stand, random_scene
from cv.tiling import iou_matrix

CLICK_SIGMA_PX = 1.5  # operator marks reference points in the UI (ФТ-КАМ-05)
TRACKED = ("box", "pallet", "container")


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0


@dataclass
class MapperStats:
    cell_ok: int = 0
    cell_total: int = 0
    errors_m: list[float] = field(default_factory=list)
    shelf_errors_m: list[float] = field(default_factory=list)

    def summary(self) -> dict:
        e, s = np.array(self.errors_m or [0]), np.array(self.shelf_errors_m or [0])
        return {
            "cell_accuracy": self.cell_ok / max(1, self.cell_total),
            "rmse_cm": float(np.sqrt((e**2).mean()) * 100),
            "p95_cm": float(np.percentile(e, 95) * 100),
            "shelf_rmse_cm": float(np.sqrt((s**2).mean()) * 100),
        }


def calibrate(stand: Stand, true_cam: CameraModel, rng: np.random.Generator) -> dict:
    """Reference markers -> floor homography and camera pose; errors on independent points."""
    markers = np.array([[x, y, 0.0] for x, y in stand.spec["markers"]])
    clicks = true_cam.project(markers) + rng.normal(0, CLICK_SIGMA_PX, (len(markers), 2))
    hom = compute_homography(clicks.tolist(), markers[:, :2].tolist())
    est_cam = CameraModel.from_markers(markers, clicks, nominal_intrinsics())

    def errors(points_xyz: np.ndarray) -> dict:
        px = true_cam.project(points_xyz) + rng.normal(0, CLICK_SIGMA_PX, (len(points_xyz), 2))
        h_xy = np.array(pixel_to_world(hom.matrix, px.tolist()))
        c_xy = est_cam.pixel_to_plane(px, points_xyz[:, 2])
        truth = points_xyz[:, :2]

        def rmse_cm(a: np.ndarray) -> float:
            return float(np.sqrt((np.linalg.norm(a - truth, axis=1) ** 2).mean()) * 100)

        return {"homography_cm": rmse_cm(h_xy), "camera_model_cm": rmse_cm(c_xy)}

    control = np.array([[x, y, 0.0] for x, y in stand.spec["control_points"]])
    shelf_pts = []
    for s in stand.spec["shelves"]:
        z = stand.shelf_top_z(s)
        for dx in (-0.12, 0.0, 0.12):
            shelf_pts.append([s["x"] + dx, s["y"], z])
    return {
        "homography": hom,
        "camera": est_cam,
        "marker_rmse_cm": hom.rmse_m * 100,
        "floor_control": errors(control),
        "shelf_top": errors(np.array(shelf_pts)),
        "camera_height_true_m": float(true_cam.centre[2]),
        "camera_height_est_m": float(est_cam.centre[2]),
    }


def match(dets, truths, iou_thr=0.5):
    """Greedy same-class matching by IoU; returns list of (det_idx, truth_idx)."""
    pairs = []
    used_d, used_t = set(), set()
    if not dets or not truths:
        return pairs
    iou = iou_matrix(np.array([d.xyxy for d in dets]), np.array([t.bbox for t in truths]))
    for flat in np.argsort(-iou, axis=None):
        i, j = np.unravel_index(flat, iou.shape)
        if iou[i, j] < iou_thr:
            break
        if i in used_d or j in used_t or dets[i].cls != truths[j].cls:
            continue
        used_d.add(i)
        used_t.add(j)
        pairs.append((int(i), int(j)))
    return pairs


def annotate(image: np.ndarray, truths, located, addr: dict, scale: float = 0.3) -> np.ndarray:
    img = cv2.cvtColor(cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA),
                       cv2.COLOR_GRAY2BGR)
    for t in truths:
        x1, y1, x2, y2 = (np.array(t.bbox) * scale).astype(int)
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 200, 0), 1)
    for ld in located:
        d = ld.det
        x1, y1, x2, y2 = (np.array(d.xyxy) * scale).astype(int)
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
        label = f"{d.cls} {d.confidence:.2f} {addr.get(ld.cell_id, '-')}"
        cv2.putText(img, label, (x1, max(10, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                    (0, 0, 255), 1, cv2.LINE_AA)
    return img


def plan_view(stand: Stand, objects, mapped_a, mapped_b, px_per_m: int = 800) -> np.ndarray:
    """Top-down plan: truth (green), floor homography (red), camera model (blue)."""
    L, W = stand.length, stand.width
    pad = 20
    img = np.full((int(W * px_per_m) + 2 * pad, int(L * px_per_m) + 2 * pad, 3), 255, np.uint8)

    def p(x, y):
        return int(pad + x * px_per_m), int(pad + (W - y) * px_per_m)

    for c in stand.cells:
        pts = np.array([p(x, y) for x, y in c.polygon], np.int32)
        cv2.polylines(img, [pts], True, (180, 180, 180), 1)
    for o, a, b in zip(objects, mapped_a, mapped_b, strict=True):
        cv2.circle(img, p(o.x, o.y), 5, (0, 170, 0), -1)
        if a:
            cv2.line(img, p(o.x, o.y), p(*a), (0, 0, 255), 1)
            cv2.circle(img, p(*a), 4, (0, 0, 255), 1)
        if b:
            cv2.circle(img, p(*b), 3, (255, 0, 0), -1)
    cv2.putText(img, "green: truth   red: floor homography   blue: camera model + surfaces",
                (pad, img.shape[0] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (60, 60, 60), 1)
    return img


def quality_checks(stand: Stand, cam: CameraModel, rng: np.random.Generator) -> dict:
    """Т-17: black, overexposed and defocused frames must be rejected; a normal one accepted."""
    base = render(stand, random_scene(stand, rng, occupancy=0.5), cam, rng, RenderConfig(),
                  scale=RENDER_SCALE).image
    cases = {
        "normal": base,
        "black": (base * 0.03).astype(np.uint8),
        "overexposed": np.clip(base.astype(np.float32) * 2.2, 0, 255).astype(np.uint8),
        "defocused": cv2.GaussianBlur(base, (0, 0), 6),
    }
    out = {}
    for name, img in cases.items():
        q = assess(img)
        out[name] = {"ok": q.ok, "reason": q.reason, "laplacian_var": round(q.laplacian_var, 1),
                     "mean": round(q.mean, 1)}
    return out


def evaluate(weights: Path, n_scenes: int, seed: int, out_root: Path, dataset: Path | None,
             device: str) -> dict:
    rng = np.random.default_rng(seed)
    stand = Stand.load()
    session = random_session(stand, rng)  # the test session: its own mount and focal error
    true_cam = session.camera
    run = out_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True, exist_ok=True)

    calib = calibrate(stand, true_cam, rng)
    surfaces = [Surface(_shelf_poly(s), stand.shelf_top_z(s)) for s in stand.spec["shelves"]]
    mapper_a = FloorHomographyMapper(calib["homography"].matrix)
    mapper_b = SurfaceAwareMapper(calib["camera"], surfaces)
    locator, addr, _zones = stand_locator(stand.cells, stand.spec["zones"])

    detector = yolo_detector(weights, DetectorConfig(scale=WORK_SCALE), device=device)
    detector.predict(np.zeros((true_cam.height, true_cam.width), np.uint8))  # CUDA warm-up
    cfg = PipelineConfig()

    counts = {c: Counts() for c in (*TRACKED, "person")}
    stats = {"floor_homography": MapperStats(), "camera_model": MapperStats()}
    count_err, times, conf_tp = [], [], []
    person_frames = {"with_person": 0, "rejected": 0, "accepted_partial": 0}
    lighting = list(LIGHTING)

    if dataset:
        for sub in ("images", "labels"):
            (dataset / sub / "test").mkdir(parents=True, exist_ok=True)

    for k in range(n_scenes):
        scene = random_scene(stand, rng, person_prob=0.15)
        rcfg = RenderConfig(lighting=lighting[k % len(lighting)],
                            noise_sigma=session.cfg.noise_sigma,
                            blur_sigma_px=session.cfg.blur_sigma_px)
        r = render(stand, scene, true_cam, rng, rcfg, scale=1.0)
        if dataset:
            name = f"test_{k:05d}"
            png = cv2.imencode(".png", to_work(r.image, 1.0))[1]
            png.tofile(str(dataset / "images" / "test" / f"{name}.png"))
            labels = "\n".join(r.yolo_labels())
            (dataset / "labels" / "test" / f"{name}.txt").write_text(labels)

        t0 = time.perf_counter()
        res = process_frame(r.image, detector, mapper_a, locator, cfg)
        times.append((time.perf_counter() - t0) * 1000)

        truths_tracked = [t for t in r.truths if t.cls in TRACKED]
        has_person = any(t.cls == "person" for t in r.truths)
        if has_person:
            person_frames["with_person"] += 1
            person_frames["rejected" if res.rejected else "accepted_partial"] += 1
        if res.rejected and not has_person:
            print(f"scene {k}: rejected unexpectedly: {res.rejected}")
        if res.rejected:
            continue

        dets = [ld.det for ld in res.detections] + res.people
        pairs = match(dets, r.truths)
        matched_d = {i for i, _ in pairs}
        matched_t = {j for _, j in pairs}
        for i, d in enumerate(dets):
            counts[d.cls].tp += i in matched_d
            counts[d.cls].fp += i not in matched_d
        for j, t in enumerate(r.truths):
            if j not in matched_t:
                counts[t.cls].fn += 1
        count_err.append(abs(len(res.detections) - len(truths_tracked)))

        mapped_a, mapped_b, objs = [], [], []
        for i, j in pairs:
            if i >= len(res.detections):
                continue  # person
            ld, obj = res.detections[i], r.truths[j].obj
            conf_tp.append(ld.det.confidence)
            for name, mapper in (("floor_homography", mapper_a), ("camera_model", mapper_b)):
                x, y = (ld.x_m, ld.y_m) if name == "floor_homography" else mapper.to_world(ld.det)
                cell = addr.get(locator.locate(x, y).cell_id)
                st = stats[name]
                st.cell_total += 1
                st.cell_ok += cell == obj.cell
                err = math.hypot(x - obj.x, y - obj.y)
                st.errors_m.append(err)
                if obj.z > 0:
                    st.shelf_errors_m.append(err)
                (mapped_a if name == "floor_homography" else mapped_b).append((x, y))
            objs.append(obj)

        if k < 4:
            cv2.imwrite(str(run / f"scene_{k:02d}_detections.jpg"),
                        annotate(r.image, r.truths, res.detections, addr))
            cv2.imwrite(str(run / f"scene_{k:02d}_plan.png"),
                        plan_view(stand, objs, mapped_a, mapped_b))

    map_metrics = None
    if dataset:
        write_data_yaml(dataset)
        from ultralytics import YOLO
        val = YOLO(str(weights)).val(data=str(dataset / "data.yaml"), split="test", imgsz=1376,
                                     device=device, verbose=False, plots=False)
        map_metrics = {
            "map50": float(val.box.map50),
            "per_class_map50": {val.names[int(c)]: float(m) for c, m in
                                zip(val.box.ap_class_index, val.box.ap50, strict=True)},
        }

    report = {
        "weights": str(weights),
        "scenes": n_scenes,
        "camera": {
            "height_true_m": calib["camera_height_true_m"],
            "height_estimated_m": calib["camera_height_est_m"],
            "fov_floor_m": np.round(true_cam.floor_footprint(), 3).tolist(),
            "mm_per_px_floor": true_cam.mm_per_px(0.0),
            "lighting_modes": lighting,
        },
        "calibration": {
            "marker_fit_rmse_cm": calib["marker_rmse_cm"],
            "floor_control_points": calib["floor_control"],
            "shelf_top_points": calib["shelf_top"],
        },
        "detection": {
            c: {"precision": v.precision, "recall": v.recall, "tp": v.tp, "fp": v.fp, "fn": v.fn}
            for c, v in counts.items()
        },
        "count_mae": float(np.mean(count_err)) if count_err else None,
        "mean_confidence_tp": float(np.mean(conf_tp)) if conf_tp else None,
        "localization": {k: v.summary() for k, v in stats.items()},
        "people": person_frames,
        "timing_ms": {"mean": float(np.mean(times)), "max": float(np.max(times))},
        "quality_checks": quality_checks(stand, true_cam, rng),
        "map": map_metrics,
    }
    (run / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report: {run}")
    return report


def _shelf_poly(s: dict) -> list[list[float]]:
    x, y, w, d = s["x"], s["y"], s["width"], s["depth"]
    return [[x - w / 2, y - d / 2], [x + w / 2, y - d / 2], [x + w / 2, y + d / 2],
            [x - w / 2, y + d / 2]]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--weights", type=Path, required=True)
    p.add_argument("--scenes", type=int, default=40)
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--out", type=Path, default=Path("storage/stand_eval"))
    p.add_argument("--dataset", type=Path, default=Path("datasets/synthetic/maquette_v1"))
    p.add_argument("--device", default="0")
    a = p.parse_args()
    evaluate(a.weights, a.scenes, a.seed, a.out, a.dataset, a.device)


if __name__ == "__main__":
    main()
