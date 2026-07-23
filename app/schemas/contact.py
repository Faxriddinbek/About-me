"""Pydantic schemas for the Contact domain, including submission validation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ContactCreate(BaseModel):
    """Validated contact-form submission.

    ``str_strip_whitespace`` trims every string first, so the length
    constraints below apply to the *stripped* value.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    message: str = Field(min_length=10, max_length=2000)

    @field_validator("message")
    @classmethod
    def _reject_degenerate_message(cls, value: str) -> str:
        """Reject content that is only whitespace or a single repeated character.

        Length limits alone would accept ``"aaaaaaaaaa"``; collapsing whitespace
        and checking the distinct-character count rejects that kind of spam.
        """
        compact = "".join(value.split())
        if len(set(compact)) <= 1:
            raise ValueError(
                "Message must contain real content, not a single repeated character."
            )
        return value


class ContactOut(BaseModel):
    """Stored contact message as returned to the admin.

    ``ip_address`` and ``user_agent`` are intentionally omitted: they exist for
    abuse tracing, not for surfacing through the API.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    message: str
    is_read: bool
    created_at: datetime


class ContactAck(BaseModel):
    """Public acknowledgement returned after a successful submission.

    Deliberately opaque — it never echoes the stored message back to the sender.
    """

    status: Literal["sent"] = "sent"
