"""Генерация синтетического датасета YOLO со стенда.

    uv run python -m cv.sim.dataset --out datasets/synthetic/maquette_v1 --train 500 --val 100
"""

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from cv.camera_model import CameraModel, nominal_intrinsics
from cv.sim.render import LIGHTING, RenderConfig, render
from cv.sim.scene import CLASS_NAMES, Stand, random_scene

RENDER_SCALE = 0.5  # rendering resolution relative to the sensor
WORK_SCALE = 0.25  # detector working resolution (DetectorConfig.scale)


@dataclass(frozen=True)
class Session:
    """One camera installation + lighting: what changes between real shooting sessions."""

    camera: CameraModel
    cfg: RenderConfig


def random_session(stand: Stand, rng: np.random.Generator) -> Session:
    c = stand.spec["camera"]
    K = nominal_intrinsics()
    K[0, 0] *= 1 + rng.normal(0, 0.007)
    K[1, 1] = K[0, 0]
    cam = CameraModel.looking_down(
        c["x"] + rng.normal(0, 0.008), c["y"] + rng.normal(0, 0.008),
        c["height_m"] + rng.uniform(-0.03, 0.03),
        tilt_x_deg=rng.normal(0, 1.0), tilt_y_deg=rng.normal(0, 1.0),
        yaw_deg=rng.normal(0, 2.0), K=K,
    )
    cfg = RenderConfig(lighting=str(rng.choice(list(LIGHTING))),
                       noise_sigma=float(rng.uniform(1.5, 4.0)),
                       blur_sigma_px=float(rng.uniform(0.4, 1.6)))
    return Session(cam, cfg)


def to_work(image: np.ndarray, from_scale: float) -> np.ndarray:
    f = WORK_SCALE / from_scale
    return cv2.resize(image, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)


def _render_one(args: tuple[str, int, str, int]) -> int:
    out, idx, split, seed = args
    rng = np.random.default_rng(seed)
    stand = Stand.load()
    session = random_session(stand, rng)
    scene = random_scene(stand, rng)
    r = render(stand, scene, session.camera, rng, session.cfg, scale=RENDER_SCALE)
    image = to_work(r.image, RENDER_SCALE)
    name = f"{split}_{idx:05d}"
    ok, buf = cv2.imencode(".png", image)
    buf.tofile(str(Path(out) / "images" / split / f"{name}.png"))
    (Path(out) / "labels" / split / f"{name}.txt").write_text("\n".join(r.yolo_labels()))
    return len(r.truths)


def write_data_yaml(out: Path) -> Path:
    lines = [f"path: {out.resolve().as_posix()}", "train: images/train", "val: images/val",
             "test: images/test", "names:"]
    lines += [f"  {i}: {n}" for i, n in enumerate(CLASS_NAMES)]
    path = out / "data.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def generate(out: Path, n_train: int, n_val: int, seed: int = 0, workers: int = 8) -> None:
    for split in ("train", "val", "test"):
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
    jobs = [(str(out), i, "train", seed * 1_000_003 + i) for i in range(n_train)]
    jobs += [(str(out), i, "val", seed * 1_000_003 + 500_000 + i) for i in range(n_val)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        counts = list(pool.map(_render_one, jobs, chunksize=4))
    write_data_yaml(out)
    meta = {"generator": "cv.sim", "stand": "maquette_a", "seed": seed, "train": n_train,
            "val": n_val, "objects": int(sum(counts)), "render_scale": RENDER_SCALE,
            "work_scale": WORK_SCALE}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(json.dumps(meta, ensure_ascii=False))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path("datasets/synthetic/maquette_v1"))
    p.add_argument("--train", type=int, default=500)
    p.add_argument("--val", type=int, default=100)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--workers", type=int, default=8)
    a = p.parse_args()
    generate(a.out, a.train, a.val, a.seed, a.workers)


if __name__ == "__main__":
    main()
