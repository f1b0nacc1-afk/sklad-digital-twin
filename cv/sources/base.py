"""Абстракция источника кадров (ФТ-КАМ-08): остальные подсистемы зависят только от неё."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np


class SourceError(RuntimeError):
    pass


@dataclass
class Frame:
    image: np.ndarray  # HxW (mono) or HxWx3 (BGR), dtype uint8 or uint16
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    pixel_format: str = "Mono8"
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    @property
    def is_mono(self) -> bool:
        return self.image.ndim == 2


@dataclass
class SourceHealth:
    online: bool
    last_frame_at: datetime | None = None
    message: str = ""


class CameraSource(ABC):
    """Lifecycle: open() -> grab()* -> close(). Usable as a context manager."""

    def __init__(self, params: dict[str, Any] | None = None):
        self.params: dict[str, Any] = dict(params or {})
        self._last_frame_at: datetime | None = None

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def grab(self) -> Frame: ...

    @abstractmethod
    def close(self) -> None: ...

    def set_params(self, **params: Any) -> None:
        self.params.update(params)

    def health(self) -> SourceHealth:
        return SourceHealth(online=True, last_frame_at=self._last_frame_at)

    def _stamp(self, frame: Frame) -> Frame:
        self._last_frame_at = frame.captured_at
        return frame

    def __enter__(self) -> "CameraSource":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
