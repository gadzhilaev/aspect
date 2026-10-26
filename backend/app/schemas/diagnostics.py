from pydantic import BaseModel, Field


class ClientErrorReportIn(BaseModel):
    source: str = Field(min_length=1, max_length=16)
    screen: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1, max_length=8000)
    exception_type: str | None = Field(default=None, max_length=255)
    stack: str | None = Field(default=None, max_length=32000)
    http_status: int | None = None
    http_code: str | None = Field(default=None, max_length=64)
    url: str | None = Field(default=None, max_length=2048)
    method: str | None = Field(default=None, max_length=16)
    details: dict | None = None
    app_version: str | None = Field(default=None, max_length=64)
    platform: str | None = Field(default=None, max_length=64)
    device_info: str | None = Field(default=None, max_length=512)
    email_attempted: str | None = Field(default=None, max_length=320)


class ClientErrorReportOut(BaseModel):
    id: str
    accepted: bool = True
