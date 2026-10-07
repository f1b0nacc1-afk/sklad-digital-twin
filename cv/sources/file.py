from pathlib import Path

import cv2
import numpy as np

from cv.sources.base import CameraSource, Frame, SourceError

SUPPORTED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}


def read_image(path: Path) -> np.ndarray:
    # imdecode instead of imread: handles non-ASCII (Cyrillic) paths on Windows.
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise SourceError(f"Не удалось прочитать изображение: {path.name}")
    if image.ndim == 3 and image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    if image.ndim == 3 and _is_gray(image):
        image = image[:, :, 0].copy()
    return image


def _is_gray(image: np.ndarray) -> bool:
    b, g, r = image[:, :, 0], image[:, :, 1], image[:, :, 2]
    return bool(np.array_equal(b, g) and np.array_equal(g, r))


class FileSource(CameraSource):
    """Serves images from a list of files (or a directory) one by one."""

    def __init__(self, paths: list[str | Path] | str | Path, params: dict | None = None):
        super().__init__(params)
        if isinstance(paths, (str, Path)) and Path(paths).is_dir():
            paths = sorted(
                p for p in Path(paths).iterdir() if p.suffix.lower() in SUPPORTED_IMAGE_EXT
            )
        elif isinstance(paths, (str, Path)):
            paths = [paths]
        self.paths = [Path(p) for p in paths]
        self._index = 0

    def open(self) -> None:
        missing = [p.name for p in self.paths if not p.exists()]
        if missing:
            raise SourceError(f"Файлы не найдены: {', '.join(missing)}")
        self._index = 0

    def grab(self) -> Frame:
        if self._index >= len(self.paths):
            raise SourceError("Файлы закончились")
        path = self.paths[self._index]
        self._index += 1
        image = read_image(path)
        fmt = ("Mono16" if image.dtype == np.uint16 else "Mono8") if image.ndim == 2 else "BGR8"
        return self._stamp(Frame(image=image, pixel_format=fmt, meta={"path": str(path)}))

    def close(self) -> None:
        pass

    @property
    def remaining(self) -> int:
        return len(self.paths) - self._index
