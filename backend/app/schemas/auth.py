from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.types import Role


class LoginIn(BaseModel):
    login: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)
    full_name: str = ""
    role: Role = Role.operator


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8)
    full_name: str | None = None
    role: Role | None = None
    is_active: bool | None = None
