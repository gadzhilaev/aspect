"""Schemas for the optional agent-loop demo stand entry panel (stage 4.8)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentDemoEntryOut(BaseModel):
    enabled: bool = True
    synthetic_notice: str
    prior_answer_notice: str
    event_id: str
    event_title: str
    is_demo: bool
    company_id: str
    company_name: str
    conversation_id: str | None = None
    news_path: str = Field(description="Existing product route to the news card")
    assistant_path: str = Field(description="Existing product route to the chat")
    scenarios_path: str = Field(description="Existing product route to discussion history")
    public_news_path: str = "/news"
