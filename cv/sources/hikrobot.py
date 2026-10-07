"""Hikrobot MV-CE200-10UM через MVS SDK (MvImport ставится вместе с MVS от производителя).

Реализация захвата — итерация 1 плана (нужна подключённая камера для отладки).
"""

from typing import Any

from cv.sources.base import CameraSource, Frame, SourceError


class HikrobotSource(CameraSource):
    def __init__(self, serial: str | None = None, params: dict[str, Any] | None = None):
        super().__init__(params)
        self.serial = serial

    def open(self) -> None:
        try:
            import MvCameraControl_class  # noqa: F401
        except ImportError as e:
            raise SourceError(
                "MVS SDK не найден: установите Hikrobot MVS и добавьте MvImport в PYTHONPATH"
            ) from e
        raise SourceError("Захват Hikrobot ещё не реализован")

    def grab(self) -> Frame:
        raise SourceError("Камера не открыта")

    def close(self) -> None:
        pass
