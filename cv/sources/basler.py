"""Basler acA5472-17um через pypylon (uv sync --extra basler)."""

from typing import Any

from cv.sources.base import CameraSource, Frame, SourceError, SourceHealth

# GenICam node names applied from Camera.params (ФТ-КАМ-02)
PARAM_NODES = {
    "exposure_us": "ExposureTime",
    "gain_db": "Gain",
    "pixel_format": "PixelFormat",
}


class BaslerSource(CameraSource):
    def __init__(self, serial: str | None = None, params: dict[str, Any] | None = None):
        super().__init__(params)
        self.serial = serial
        self._camera = None

    def open(self) -> None:
        try:
            from pypylon import pylon
        except ImportError as e:
            raise SourceError("pypylon не установлен: uv sync --extra basler") from e
        factory = pylon.TlFactory.GetInstance()
        devices = factory.EnumerateDevices()
        if self.serial:
            devices = [d for d in devices if d.GetSerialNumber() == self.serial]
        if not devices:
            raise SourceError("Камера Basler не найдена")
        self._camera = pylon.InstantCamera(factory.CreateDevice(devices[0]))
        self._camera.Open()
        self._apply_params()

    def _apply_params(self) -> None:
        cam = self._camera
        cam.ExposureAuto.SetValue("Off")
        cam.GainAuto.SetValue("Off")
        for key, node in PARAM_NODES.items():
            if key in self.params:
                getattr(cam, node).SetValue(self.params[key])

    def set_params(self, **params: Any) -> None:
        super().set_params(**params)
        if self._camera is not None and self._camera.IsOpen():
            self._apply_params()

    def grab(self) -> Frame:
        if self._camera is None:
            raise SourceError("Камера не открыта")
        timeout_ms = int(self.params.get("timeout_ms", 5000))
        result = self._camera.GrabOne(timeout_ms)
        try:
            if not result.GrabSucceeded():
                raise SourceError(f"Ошибка захвата: {result.ErrorDescription}")
            image = result.Array.copy()
            fmt = str(self._camera.PixelFormat.GetValue())
        finally:
            result.Release()
        return self._stamp(Frame(image=image, pixel_format=fmt, meta={"serial": self.serial}))

    def close(self) -> None:
        if self._camera is not None:
            self._camera.Close()
            self._camera = None

    def health(self) -> SourceHealth:
        online = self._camera is not None and self._camera.IsOpen()
        return SourceHealth(online=online, last_frame_at=self._last_frame_at)
