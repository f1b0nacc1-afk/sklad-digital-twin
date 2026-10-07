"""КТ-0: получить один кадр с камеры, сохранить PNG и вывести оценку качества.

    uv sync --extra basler
    uv run python scripts/grab_one.py --vendor basler --exposure 20000 --out storage/first.png
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402

from cv.quality import assess  # noqa: E402
from cv.sources import SourceError, create_source  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", choices=["basler", "hikrobot"], default="basler")
    parser.add_argument("--serial", default=None)
    parser.add_argument("--exposure", type=float, default=20000, help="мкс")
    parser.add_argument("--gain", type=float, default=0.0, help="дБ")
    parser.add_argument("--out", type=Path, default=Path("storage/grab_one.png"))
    args = parser.parse_args()

    params = {"exposure_us": args.exposure, "gain_db": args.gain}
    try:
        with create_source(args.vendor, serial=args.serial, params=params) as cam:
            t0 = time.perf_counter()
            frame = cam.grab()
            dt = time.perf_counter() - t0
    except SourceError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(args.out.suffix or ".png", frame.image)
    if not ok:
        print("Не удалось закодировать кадр", file=sys.stderr)
        return 1
    buf.tofile(str(args.out))

    q = assess(frame.image)
    print(f"Кадр {frame.width}×{frame.height} {frame.pixel_format}, захват {dt * 1000:.0f} мс")
    print(f"Яркость {q.mean:.0f}, пересвет {q.overexposed_ratio:.1%}, "
          f"резкость {q.sharpness:.1f} (var Laplacian {q.laplacian_var:.0f}) -> "
          f"{'OK' if q.ok else q.reason}")
    print(f"Сохранено: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
