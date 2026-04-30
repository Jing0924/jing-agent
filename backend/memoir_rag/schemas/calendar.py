"""Request/response models for calendar NLP → Google Calendar API."""

from __future__ import annotations

from typing import Literal, Union

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

    result: Literal["created"] = "created"
    id: str
    html_link: str = Field(serialization_alias="htmlLink")
    summary: str
    start: str
    end: str


class CalendarEventDeletedResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    result: Literal["deleted"] = "deleted"
    id: str
    summary: str
    start: str
    end: str


CalendarFromTextResponse = Union[CalendarEventCreatedResponse, CalendarEventDeletedResponse]
