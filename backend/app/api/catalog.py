from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.models import ObjectType
from app.schemas.catalog import ObjectTypeCreate, ObjectTypeOut, ObjectTypeUpdate
from app.services.audit import audit

router = APIRouter(prefix="/api/object-types", tags=["catalog"])


@router.get("", response_model=list[ObjectTypeOut])
def list_object_types(db: DbSession, _: CurrentUser) -> list[ObjectType]:
    return list(db.scalars(select(ObjectType).order_by(ObjectType.id)))


@router.post("", response_model=ObjectTypeOut, status_code=status.HTTP_201_CREATED)
def create_object_type(data: ObjectTypeCreate, db: DbSession, admin: AdminUser) -> ObjectType:
    if db.scalar(select(ObjectType).where(ObjectType.code == data.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Тип с таким кодом уже существует")
    ot = ObjectType(**data.model_dump())
    db.add(ot)
    db.flush()
    audit(db, admin, "create", "object_type", ot.id, data.model_dump())
    db.commit()
    return ot


@router.patch("/{type_id}", response_model=ObjectTypeOut)
def update_object_type(
    type_id: int, data: ObjectTypeUpdate, db: DbSession, admin: AdminUser
) -> ObjectType:
    ot = db.get(ObjectType, type_id)
    if ot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Тип не найден")
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(ot, key, value)
    audit(db, admin, "update", "object_type", ot.id, changes)
    db.commit()
    return ot
