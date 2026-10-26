from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SupportMessageOut(BaseModel):
    id: str
    role: Literal["user", "support", "system", "operator"]
    content: str
    client_message_id: str | None = None
    created_at: datetime


class SupportThreadOut(BaseModel):
    id: str
    status: Literal["open", "closed", "waiting_operator", "with_operator"]
    handler: Literal["ai", "operator"] = "ai"
    subject: str | None = None
    company_id: str | None = None
    ticket: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[SupportMessageOut] = Field(default_factory=list)


class SupportMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    client_message_id: str | None = Field(default=None, max_length=64)
    company_id: str | None = Field(default=None, max_length=36)


class SupportPostMessageOut(BaseModel):
    user_message: SupportMessageOut
    support_message: SupportMessageOut | None = None
    reused: bool = False
