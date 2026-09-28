from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ClientName = Literal["WATCH", "DESKTOP", "CORE", "MOBILE"]
ItemStatus = Literal["PENDING", "COMPLETED"]


class SharedContextCreate(BaseModel):
    source: ClientName
    target: ClientName
    kind: str = Field(default="REMINDER", min_length=1, max_length=40)
    content: str = Field(..., min_length=1, max_length=1000)
    remind_at: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("remind_at")
    @classmethod
    def require_timezone_on_reminder(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("remind_at must include a timezone offset")
        return value


class SharedContextComplete(BaseModel):
    completed_by: ClientName
