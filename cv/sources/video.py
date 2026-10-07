from pathlib import Path

import cv2

from cv.sources.base import CameraSource, Frame, SourceError


class VideoSource(CameraSource):
    """Extracts frames from a video file with a fixed time step (ТЗ 4.1.3: 1 frame / 2 s)."""

    def __init__(self, path: str | Path, step_s: float = 2.0, params: dict | None = None):
        super().__init__(params)
        self.path = Path(path)
        self.step_s = step_s
        self._cap: cv2.VideoCapture | None = None
        self._next_ms = 0.0

    def open(self) -> None:
        if not self.path.exists():
            raise SourceError(f"Видео не найдено: {self.path.name}")
        self._cap = cv2.VideoCapture(str(self.path))
        if not self._cap.isOpened():
            raise SourceError(f"Не удалось открыть видео: {self.path.name}")
        self._next_ms = 0.0

    def grab(self) -> Frame:
        if self._cap is None:
            raise SourceError("Источник не открыт")
        self._cap.set(cv2.CAP_PROP_POS_MSEC, self._next_ms)
        ok, image = self._cap.read()
        if not ok:
            raise SourceError("Видео закончилось")
        position_ms = self._next_ms
        self._next_ms += self.step_s * 1000
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return self._stamp(Frame(
            image=image, pixel_format="Mono8",
            meta={"path": str(self.path), "position_ms": position_ms},
        ))

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
