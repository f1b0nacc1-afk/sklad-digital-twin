from enum import StrEnum

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Role(StrEnum):
    admin = "admin"
    operator = "operator"
    viewer = "viewer"


class ZoneType(StrEnum):
    storage = "storage"
    receiving = "receiving"
    shipping = "shipping"
    loading = "loading"
    aisle = "aisle"


class ObjectStatus(StrEnum):
    active = "active"
    missing = "missing"
    removed = "removed"


class ScanSource(StrEnum):
    camera = "camera"
    image = "image"
    video = "video"
    schedule = "schedule"


class ScanStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"
    rejected = "rejected"


class EventType(StrEnum):
    appeared = "appeared"
    moved = "moved"
    disappeared = "disappeared"
    confirmed = "confirmed"
    edited = "edited"


class CameraStatus(StrEnum):
    online = "online"
    offline = "offline"
    unknown = "unknown"
