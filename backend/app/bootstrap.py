"""Идемпотентное начальное заполнение: администратор, справочник типов, настройки.

Запуск: python -m app.bootstrap
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import ObjectType, Setting, User
from app.models.types import Role

# ТЗ п. 3.2
DEFAULT_OBJECT_TYPES = [
    {"code": "box", "name": "Коробка", "is_tracked": True, "color": "#d4a373", "model_class_index": 0},
    {"code": "pallet", "name": "Паллета", "is_tracked": True, "color": "#8d6e63", "model_class_index": 1},
    {"code": "container", "name": "Контейнер", "is_tracked": True, "color": "#4f86c6", "model_class_index": 2},
    {"code": "person", "name": "Человек", "is_tracked": False, "color": "#e63946", "model_class_index": 3},
    {"code": "forklift", "name": "Погрузочная техника", "is_tracked": False, "color": "#f4a261"},
    {"code": "rack", "name": "Стеллаж", "is_tracked": False, "color": "#6c757d"},
]

# ТЗ ФТ-CV-05, ФТ-ЦД-02/03, ФТ-СКН-07, НФТ-Х-02
DEFAULT_SETTINGS = {
    "confidence_threshold": 0.5,
    "match_distance_m": 0.03,
    "disappear_after_scans": 2,
    "schedule_interval_min": 5,
    "schedule_enabled": False,
    "image_retention_days": 30,
    "max_occlusion_ratio": 0.2,
    "blur_threshold": 100.0,
}


def bootstrap(db: Session) -> None:
    settings = get_settings()
    if db.scalar(select(User).limit(1)) is None:
        db.add(User(
            login=settings.admin_login,
            password_hash=hash_password(settings.admin_password),
            full_name="Администратор",
            role=Role.admin,
        ))
    existing_types = set(db.scalars(select(ObjectType.code)))
    for data in DEFAULT_OBJECT_TYPES:
        if data["code"] not in existing_types:
            db.add(ObjectType(**data))
    existing_keys = set(db.scalars(select(Setting.key)))
    for key, value in DEFAULT_SETTINGS.items():
        if key not in existing_keys:
            db.add(Setting(key=key, value=value))
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as session:
        bootstrap(session)
    print("bootstrap: ok")
