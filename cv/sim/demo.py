"""Демо-прогон виртуального стенда для веб-интерфейса.

Рендерит кадры камеры, распознаёт их обученной моделью и складывает в storage/stand_demo/<run>/
всё, что показывает страница «Виртуальный стенд»: кадр, крупный план, разметку, детекции, план,
таблицу объектов, образцы синтетического датасета и итоги испытания.

    uv run python -m cv.sim.demo --weights models_store/sklad-sim-v1.pt --scenes 12
"""

import argparse
import json
import math
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from cv.detector import DetectorConfig, yolo_detector
from cv.pipeline import (
    FloorHomographyMapper,
    PipelineConfig,
    Surface,
    SurfaceAwareMapper,
    process_frame,
    stand_locator,
)
from cv.sim.dataset import WORK_SCALE, random_session
from cv.sim.evaluate import _shelf_poly, calibrate, match, plan_view
from cv.sim.render import LIGHTING, RenderConfig, render
from cv.sim.scene import CLASS_NAMES, Stand, random_scene

COLORS = {"box": (40, 40, 230), "pallet": (230, 120, 20), "container": (30, 170, 230),
          "person": (200, 40, 200)}
TRUTH_COLOR = (0, 200, 0)


def _to_bgr(image: np.ndarray, scale: float) -> np.ndarray:
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)


def _label(img: np.ndarray, text: str, x: int, y: int, color: tuple) -> None:
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
    y = max(h + 6, y)
    cv2.rectangle(img, (x, y - h - 6), (x + w + 6, y), color, -1)
    cv2.putText(img, text, (x + 3, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2,
                cv2.LINE_AA)


def _draw_truths(img: np.ndarray, truths, scale: float) -> np.ndarray:
    for t in truths:
        x1, y1, x2, y2 = (np.array(t.bbox) * scale).astype(int)
        cv2.rectangle(img, (x1, y1), (x2, y2), TRUTH_COLOR, 2)
        _label(img, f"{t.cls} {t.obj.cell or '-'}" if t.obj else t.cls, x1, y1, TRUTH_COLOR)
    return img


def _draw_detections(img: np.ndarray, rows: list[dict], people, scale: float) -> np.ndarray:
    for r in rows:
        x1, y1, x2, y2 = (np.array(r["bbox"]) * scale).astype(int)
        color = COLORS[r["cls"]] if r["status"] != "false_positive" else (0, 0, 255)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        _label(img, f"{r['cls']} {r['confidence']:.2f} {r['cell'] or '-'}", x1, y1, color)
    for p in people:
        x1, y1, x2, y2 = (np.array(p.xyxy) * scale).astype(int)
        cv2.rectangle(img, (x1, y1), (x2, y2), COLORS["person"], 2)
        _label(img, f"person {p.confidence:.2f}", x1, y1, COLORS["person"])
    return img


def _crop(image: np.ndarray, centre_uv: np.ndarray, size=(1200, 800)) -> np.ndarray:
    h, w = image.shape
    cx, cy = int(centre_uv[0]), int(centre_uv[1])
    x0 = int(np.clip(cx - size[0] // 2, 0, w - size[0]))
    y0 = int(np.clip(cy - size[1] // 2, 0, h - size[1]))
    return image[y0:y0 + size[1], x0:x0 + size[0]]


def _dataset_samples(dataset: Path, out: Path, n: int = 8) -> dict | None:
    images = sorted((dataset / "images" / "train").glob("*.png"))
    if not images:
        return None
    out.mkdir(parents=True, exist_ok=True)
    class_counts: Counter[str] = Counter()
    for lbl in (dataset / "labels" / "train").glob("*.txt"):
        for line in lbl.read_text().splitlines():
            class_counts[CLASS_NAMES[int(line.split()[0])]] += 1
    samples = []
    for i, path in enumerate(images[:: max(1, len(images) // n)][:n]):
        img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_GRAYSCALE)
        bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        h, w = img.shape
        lines = (dataset / "labels" / "train" / f"{path.stem}.txt").read_text().splitlines()
        for line in lines:
            c, cx, cy, bw, bh = line.split()
            cx, cy, bw, bh = float(cx) * w, float(cy) * h, float(bw) * w, float(bh) * h
            name = CLASS_NAMES[int(c)]
            p1, p2 = (int(cx - bw / 2), int(cy - bh / 2)), (int(cx + bw / 2), int(cy + bh / 2))
            cv2.rectangle(bgr, p1, p2, COLORS[name], 2)
        cv2.imwrite(str(out / f"sample_{i}.jpg"), bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
        samples.append({"file": f"dataset/sample_{i}.jpg", "source": path.name,
                        "objects": len(lines)})
    meta_path = dataset / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    return {"meta": meta, "class_counts": dict(class_counts), "samples": samples,
            "image_size": [int(w), int(h)]}


def run_demo(weights: Path, n_scenes: int, seed: int, out_root: Path, dataset: Path,
             eval_root: Path, device: str) -> Path:
    rng = np.random.default_rng(seed)
    stand = Stand.load()
    session = random_session(stand, rng)
    cam = session.camera
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run = out_root / run_id
    (run / "scenes").mkdir(parents=True, exist_ok=True)

    calib = calibrate(stand, cam, rng)
    surfaces = [Surface(_shelf_poly(s), stand.shelf_top_z(s)) for s in stand.spec["shelves"]]
    mapper_h = FloorHomographyMapper(calib["homography"].matrix)
    mapper_c = SurfaceAwareMapper(calib["camera"], surfaces)
    locator, addr, zones = stand_locator(stand.cells, stand.spec["zones"])
    detector = yolo_detector(weights, DetectorConfig(scale=WORK_SCALE), device=device)
    detector.predict(np.zeros((cam.height, cam.width), np.uint8))
    cfg = PipelineConfig()
    shelf_uv = cam.project(np.array([[s["x"], s["y"], stand.shelf_top_z(s)]
                                     for s in stand.spec["shelves"]]))

    scenes = []
    lighting = list(LIGHTING)
    for k in range(n_scenes):
        scene = random_scene(stand, rng, person_prob=0.2)
        rcfg = RenderConfig(lighting=lighting[k % len(lighting)],
                            noise_sigma=session.cfg.noise_sigma,
                            blur_sigma_px=session.cfg.blur_sigma_px)
        r = render(stand, scene, cam, rng, rcfg, scale=1.0)
        res = process_frame(r.image, detector, mapper_c, locator, cfg)

        dets = [ld.det for ld in res.detections]
        pairs = dict(match(dets, r.truths))
        truth_used = set(pairs.values())
        rows = []
        for i, ld in enumerate(res.detections):
            d = ld.det
            hx, hy = mapper_h.to_world(d)
            row = {
                "cls": d.cls, "confidence": round(d.confidence, 3),
                "bbox": [round(v, 1) for v in d.xyxy],
                "x_m": round(ld.x_m, 4), "y_m": round(ld.y_m, 4),
                "cell": addr.get(ld.cell_id), "zone": zones.get(ld.zone_id),
                "cell_homography": addr.get(locator.locate(hx, hy).cell_id),
                "status": "false_positive",
            }
            if i in pairs:
                obj = r.truths[pairs[i]].obj
                row.update({
                    "status": "ok" if row["cell"] == obj.cell else "wrong_cell",
                    "true_cell": obj.cell, "true_x_m": round(obj.x, 4),
                    "true_y_m": round(obj.y, 4), "on_shelf": obj.z > 0,
                    "error_cm": round(math.hypot(ld.x_m - obj.x, ld.y_m - obj.y) * 100, 2),
                    "error_homography_cm": round(math.hypot(hx - obj.x, hy - obj.y) * 100, 2),
                })
            rows.append(row)
        missed = [{"cls": t.cls, "cell": t.obj.cell if t.obj else None}
                  for j, t in enumerate(r.truths)
                  if j not in truth_used and t.cls != "person" and not res.rejected]

        sid = f"scene_{k:02d}"
        sdir = run / "scenes" / sid
        sdir.mkdir(exist_ok=True)
        cv2.imwrite(str(sdir / "frame.jpg"), _to_bgr(r.image, WORK_SCALE),
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
        cv2.imwrite(str(sdir / "crop.png"), _crop(r.image, shelf_uv[k % len(shelf_uv)]))
        cv2.imwrite(str(sdir / "truth.jpg"),
                    _draw_truths(_to_bgr(r.image, WORK_SCALE), r.truths, WORK_SCALE),
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
        annotated = _draw_detections(_to_bgr(r.image, WORK_SCALE), rows, res.people, WORK_SCALE)
        if res.rejected:
            cv2.putText(annotated, f"REJECTED: {res.rejected}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.imwrite(str(sdir / "detections.jpg"), annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
        matched = [(rw, r.truths[pairs[i]].obj) for i, rw in enumerate(rows) if i in pairs]
        cv2.imwrite(str(sdir / "plan.png"), plan_view(
            stand, [o for _, o in matched],
            [mapper_h.to_world(res.detections[i].det) for i in range(len(rows)) if i in pairs],
            [(rw["x_m"], rw["y_m"]) for rw, _ in matched]))

        info = {
            "id": sid, "lighting": rcfg.lighting, "rejected": res.rejected,
            "quality": {"ok": res.quality.ok, "reason": res.quality.reason,
                        "mean": round(res.quality.mean, 1),
                        "laplacian_var": round(res.quality.laplacian_var, 1),
                        "sharpness": round(res.quality.sharpness, 1)},
            "timings_ms": {**{k2: round(v, 1) for k2, v in res.timings_ms.items()},
                           "total": round(sum(res.timings_ms.values()), 1)},
            "truth_count": sum(t.cls != "person" for t in r.truths),
            "has_person": any(t.cls == "person" for t in r.truths),
            "people": [{"confidence": round(p.confidence, 3)} for p in res.people],
            "detections": rows, "missed": missed,
            "distractors": [d["kind"] for d in scene.distractors],
            "files": {n: f"scenes/{sid}/{n}" for n in
                      ("frame.jpg", "crop.png", "truth.jpg", "detections.jpg", "plan.png")},
        }
        (sdir / "scene.json").write_text(json.dumps(info, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
        scenes.append(info)
        print(f"{sid}: {len(rows)} detections, rejected={res.rejected}")

    det_rows = [d for s in scenes for d in s["detections"]]
    matched_rows = [d for d in det_rows if d["status"] != "false_positive"]
    reports = sorted(eval_root.glob("*/report.json"))
    summary = {
        "run": run_id,
        "created": datetime.now().isoformat(timespec="seconds"),
        "weights": weights.name,
        "stand": {"name": "maquette_a", "size_m": stand.spec["size"],
                  "zones": stand.spec["zones"], "cells": len(stand.cells)},
        "camera": {
            "sensor": [cam.width, cam.height], "height_true_m": round(float(cam.centre[2]), 4),
            "height_estimated_m": round(float(calib["camera"].centre[2]), 4),
            "fov_floor_m": np.round(np.ptp(cam.floor_footprint(), axis=0), 3).tolist(),
            "mm_per_px_floor": round(cam.mm_per_px(0.0), 3),
            "work_scale": WORK_SCALE,
        },
        "calibration": {
            "marker_fit_rmse_cm": round(calib["marker_rmse_cm"], 3),
            "floor_control_points": calib["floor_control"],
            "shelf_top_points": calib["shelf_top"],
        },
        "totals": {
            "scenes": len(scenes),
            "rejected": sum(bool(s["rejected"]) for s in scenes),
            "detections": len(det_rows),
            "false_positives": len(det_rows) - len(matched_rows),
            "missed": sum(len(s["missed"]) for s in scenes),
            "cell_accuracy": (sum(d["status"] == "ok" for d in matched_rows)
                              / max(1, len(matched_rows))),
            "cell_accuracy_homography": (sum(d["cell_homography"] == d["true_cell"]
                                             for d in matched_rows) / max(1, len(matched_rows))),
            "mean_time_ms": round(float(np.mean([s["timings_ms"].get("total", 0)
                                                 for s in scenes])), 1),
        },
        "evaluation": (json.loads(reports[-1].read_text(encoding="utf-8")) if reports else None),
        "dataset": _dataset_samples(dataset, run / "dataset"),
        "scenes": [{"id": s["id"], "lighting": s["lighting"], "rejected": s["rejected"],
                    "detections": len(s["detections"]), "truth_count": s["truth_count"],
                    "has_person": s["has_person"]} for s in scenes],
    }
    (run / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    latest = out_root / "latest.txt"
    latest.write_text(run_id, encoding="utf-8")
    print(f"demo: {run}")
    return run


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--weights", type=Path, default=Path("models_store/sklad-sim-v1.pt"))
    p.add_argument("--scenes", type=int, default=12)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", type=Path, default=Path("storage/stand_demo"))
    p.add_argument("--dataset", type=Path, default=Path("datasets/synthetic/maquette_v1"))
    p.add_argument("--eval", type=Path, default=Path("storage/stand_eval"))
    p.add_argument("--device", default="0")
    p.add_argument("--clean", action="store_true", help="remove previous demo runs")
    a = p.parse_args()
    if a.clean and a.out.exists():
        shutil.rmtree(a.out)
    run_demo(a.weights, a.scenes, a.seed, a.out, a.dataset, a.eval, a.device)


if __name__ == "__main__":
    main()
