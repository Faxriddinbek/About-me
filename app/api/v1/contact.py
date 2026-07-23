"""Public contact endpoint (rate limited).

NOTE: this module deliberately does NOT use ``from __future__ import
annotations``. slowapi wraps the endpoint, and FastAPI would then resolve the
(stringized) type hints against slowapi's module globals — where ``ContactCreate``
etc. don't exist — mis-reading body/dependency params as query params. Real
annotation objects avoid that.
"""

from fastapi import APIRouter, BackgroundTasks, Request

from app.api.deps import ContactServiceDep, get_client_ip
from app.api.limiter import limiter
from app.schemas.contact import ContactAck, ContactCreate

router = APIRouter(prefix="/contact", tags=["contact"])

# Per-IP submission cap enforced by slowapi at the edge (the service also
# enforces the same policy against the database as a durable backstop).
_CONTACT_RATE_LIMIT = "3/hour"


@router.post(
    "",
    response_model=ContactAck,
    status_code=201,
    summary="Submit a contact message",
    description=(
        "Validate and store a contact message, then notify the site owner out "
        "of band. Rate limited to 3 requests per hour per IP."
    ),
)
@limiter.limit(_CONTACT_RATE_LIMIT)
async def submit_contact(
    request: Request,
    payload: ContactCreate,
    background: BackgroundTasks,
    service: ContactServiceDep,
) -> ContactAck:
    await service.submit(
        payload,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        background=background,
    )
    return ContactAck()
