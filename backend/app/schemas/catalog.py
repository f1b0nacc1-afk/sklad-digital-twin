from pydantic import BaseModel, ConfigDict, Field


class ObjectTypeBase(BaseModel):
    code: str = Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    is_tracked: bool = True
    icon: str | None = None
    color: str | None = None
    model_class_index: int | None = None


class ObjectTypeCreate(ObjectTypeBase):
    pass


class ObjectTypeUpdate(BaseModel):
    name: str | None = None
    is_tracked: bool | None = None
    icon: str | None = None
    color: str | None = None
    model_class_index: int | None = None


class ObjectTypeOut(ObjectTypeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
