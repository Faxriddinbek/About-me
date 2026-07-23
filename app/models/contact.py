"""The ``ContactMessage`` model — a submission from the site's contact form."""

from sqlalchemy import String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContactMessage(Base):
    """A message submitted through the contact form.

    ``ip_address`` and ``user_agent`` are captured for abuse tracing and
    rate-limit forensics only — not analytics.
    """

    __tablename__ = "contact_messages"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)  # RFC 5321 max
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Nullable: a proxy or privacy setting may strip these before they reach us.
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 max
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Indexed: the admin inbox filters unread messages (`WHERE is_read = false`).
    is_read: Mapped[bool] = mapped_column(
        default=False, server_default=text("false"), index=True, nullable=False
    )
