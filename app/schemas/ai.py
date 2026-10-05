"""Request schema for the AI chat endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import Lang


class ChatMessage(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    """The conversation so far; the last message is the visitor's question.

    The client sends the history because the server keeps none — nothing is
    stored, so there is no chat log to protect or clean up.
    """

    messages: list[ChatMessage] = Field(min_length=1, max_length=30)
    lang: Lang = "uz"

    @model_validator(mode="after")
    def _ends_with_question(self) -> ChatRequest:
        if self.messages[-1].role != "user":
            raise ValueError("The last message must be from the user.")
        return self
