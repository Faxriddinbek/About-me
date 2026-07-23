"""The ``MediaItem`` model and its ``MediaType`` enumeration."""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MediaType(StrEnum):
    """Kind of gallery media. ``StrEnum`` gives type-safe members whose values
    are exactly the strings persisted to the database."""

    PHOTO = "photo"
    VIDEO = "video"


class MediaItem(Base):
    """A gallery item — either a photo or a video."""

    __tablename__ = "media_items"

    # ``values_callable`` makes SQLAlchemy persist the enum *values* ("photo",
    # "video") instead of its default of member *names* ("PHOTO", "VIDEO"), so
    # the stored representation matches the StrEnum's string values.
    media_type: Mapped[MediaType] = mapped_column(
        SAEnum(
            MediaType,
            name="media_type",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    url: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    title_uz: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title_en: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Manual sort position; indexed on its own for the admin listing that orders
    # every row regardless of visibility.
    display_order: Mapped[int] = mapped_column(
        default=0, server_default=text("0"), index=True, nullable=False
    )

    is_visible: Mapped[bool] = mapped_column(
        default=True, server_default=text("true"), nullable=False
    )

    __table_args__ = (
        # Same access pattern as projects: the gallery lists visible items in
        # order, so a composite (is_visible, display_order) serves filter + sort.
        Index("ix_media_items_visible_order", "is_visible", "display_order"),
    )
