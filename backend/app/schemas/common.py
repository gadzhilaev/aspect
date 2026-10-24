from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MessageOut(BaseModel):
    message: str
    details: dict[str, Any] | None = None


class CursorPage(BaseModel):
    items: list[Any]
    next_cursor: str | None = None
    limit: int = 20


class IndustryOut(BaseModel):
    id: str
    name: str


INDUSTRIES = [
    IndustryOut(id="equipment", name="Производство оборудования"),
    IndustryOut(id="electronics", name="Электроника"),
    IndustryOut(id="logistics", name="Логистика"),
    IndustryOut(id="retail", name="Ритейл"),
    IndustryOut(id="energy", name="Энергетика"),
    IndustryOut(id="other", name="Другое"),
]
