"""Обучение детектора YOLO.

    uv run python -m cv.training.train --data datasets/synthetic/maquette_v1/data.yaml \
        --name sklad-sim-v1 --epochs 60
"""

import argparse
import json
import shutil
from pathlib import Path

import yaml

MODELS_DIR = Path("models_store")


def train(data: Path, name: str, base: str, epochs: int, imgsz: int, batch: int,
          device: str, workers: int = 2, resume: bool = False) -> Path:
    from ultralytics import YOLO

    run_dir = Path("runs") / name
    if resume:
        # On Windows every dataloader worker re-imports torch; few workers keep commit memory low.
        YOLO(str(run_dir / "weights" / "last.pt")).train(resume=True, workers=workers)
    else:
        YOLO(base).train(
            data=str(data), epochs=epochs, imgsz=imgsz, batch=batch, device=device,
            project=str(Path("runs").resolve()), name=name, exist_ok=True, workers=workers,
            patience=25, close_mosaic=10, plots=True,
            # Monochrome camera: no hue/saturation; brightness varies with lighting.
            hsv_h=0.0, hsv_s=0.0, hsv_v=0.35,
            # Top view: orientation is arbitrary, scale is fixed by the mount.
            fliplr=0.5, flipud=0.5, degrees=10, scale=0.2, translate=0.1, mosaic=1.0,
        )
    best = run_dir / "weights" / "best.pt"
    MODELS_DIR.mkdir(exist_ok=True)
    target = MODELS_DIR / f"{name}.pt"
    shutil.copy(best, target)

    args = yaml.safe_load((run_dir / "args.yaml").read_text(encoding="utf-8"))
    val = YOLO(str(target)).val(data=args["data"], imgsz=args["imgsz"], split="val",
                                device=device, verbose=False, plots=False)
    names = val.names
    metrics = {
        "map50": float(val.box.map50),
        "map50_95": float(val.box.map),
        "per_class_map50": {names[int(c)]: float(m) for c, m in
                            zip(val.box.ap_class_index, val.box.ap50, strict=True)},
        **{k: args[k] for k in ("model", "epochs", "imgsz", "batch", "data")},
    }
    (MODELS_DIR / f"{name}.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return target


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--name", default="sklad-sim-v1")
    p.add_argument("--base", default="yolo11s.pt")
    p.add_argument("--epochs", type=int, default=60)
    p.add_argument("--imgsz", type=int, default=1376)
    p.add_argument("--batch", type=int, default=4)  # 1376 px, 10 GB VRAM
    p.add_argument("--device", default="0")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    train(a.data, a.name, a.base, a.epochs, a.imgsz, a.batch, a.device, a.workers, a.resume)


if __name__ == "__main__":
    main()
