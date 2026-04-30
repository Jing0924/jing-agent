"""Request/response models for calendar NLP → Google Calendar API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CalendarFromTextBody(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def text_non_empty_after_strip(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Text cannot be empty.")
        return s


class CalendarStatusResponse(BaseModel):
    configured: bool


class CalendarEventCreatedResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    html_link: str = Field(serialization_alias="htmlLink")
    summary: str
    start: str
    end: str
