from typing import Any

from cv.sources.base import CameraSource, SourceError


def create_source(connection: str, *, serial: str | None = None, path: str | None = None,
                  params: dict[str, Any] | None = None) -> CameraSource:
    """Map Camera.connection to a CameraSource implementation."""
    if connection == "basler":
        from cv.sources.basler import BaslerSource
        return BaslerSource(serial=serial, params=params)
    if connection == "hikrobot":
        from cv.sources.hikrobot import HikrobotSource
        return HikrobotSource(serial=serial, params=params)
    if connection == "file":
        from cv.sources.file import FileSource
        if not path:
            raise SourceError("Для источника file нужен путь")
        return FileSource(path, params=params)
    if connection == "video":
        from cv.sources.video import VideoSource
        if not path:
            raise SourceError("Для источника video нужен путь")
        step = float((params or {}).get("step_s", 2.0))
        return VideoSource(path, step_s=step, params=params)
    raise SourceError(f"Неизвестный тип подключения: {connection}")
