from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.auth import LoginIn, TokenOut, UserCreate, UserOut, UserUpdate
from app.services.audit import audit

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn, db: DbSession) -> TokenOut:
    user = db.scalar(select(User).where(User.login == data.login))
    if user is None or not user.is_active or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    audit(db, user, "login", "user", user.id)
    db.commit()
    return TokenOut(access_token=create_access_token(user.id, user.role), role=user.role)


@router.get("/auth/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: DbSession, _: AdminUser) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, db: DbSession, admin: AdminUser) -> User:
    if db.scalar(select(User).where(User.login == data.login)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким логином уже существует")
    user = User(
        login=data.login,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    db.add(user)
    db.flush()
    audit(db, admin, "create", "user", user.id, {"login": user.login, "role": user.role})
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db: DbSession, admin: AdminUser) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    changes = data.model_dump(exclude_unset=True)
    if password := changes.pop("password", None):
        user.password_hash = hash_password(password)
    for key, value in changes.items():
        setattr(user, key, value)
    audit(db, admin, "update", "user", user.id, {**changes, "password_changed": bool(password)})
    db.commit()
    return user
