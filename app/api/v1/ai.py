"""Public AI chat endpoint (rate limited, streamed).

NOTE: like ``contact.py`` this module does NOT use ``from __future__ import
annotations`` — slowapi wraps the endpoint, and stringized hints would be
resolved against slowapi's globals.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import SettingsDep, get_project_repository
from app.api.limiter import limiter
from app.repositories.project import ProjectRepository
from app.schemas.ai import ChatRequest
from app.services.ai import AiChatService

router = APIRouter(prefix="/ai", tags=["ai"])

# Each answer costs provider quota, so the cap is per IP and fairly tight. Two
# windows: a burst limit and an hourly one.
_AI_RATE_LIMIT = "6/minute;30/hour"


def get_ai_service(
    settings: SettingsDep,
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> AiChatService:
    return AiChatService(settings, projects)


@router.post(
    "/chat",
    response_class=StreamingResponse,
    summary="Ask the site's AI assistant",
    description=(
        "Send the conversation so far; the reply streams back as plain UTF-8 "
        "text chunks. Answers only about the site owner. Nothing is stored. "
        "503 `ai_unavailable` when not configured, 503 `ai_busy` when the "
        "provider's quota is exhausted, 502 on provider errors. Rate limited "
        "to 6/minute and 30/hour per IP."
    ),
)
@limiter.limit(_AI_RATE_LIMIT)
async def chat(
    request: Request,
    payload: ChatRequest,
    service: Annotated[AiChatService, Depends(get_ai_service)],
) -> StreamingResponse:
    chunks = await service.stream_reply(payload.messages, payload.lang)
    return StreamingResponse(
        chunks,
        media_type="text/plain; charset=utf-8",
        # Stop nginx from buffering the stream, so text appears as it arrives.
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
