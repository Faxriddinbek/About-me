"""The ``Project`` model — a portfolio project card shown on the site."""

from sqlalchemy import JSON, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Project(Base):
    """A portfolio project.

    Bilingual text lives in paired ``_uz`` / ``_en`` columns rather than a
    separate translation table: the field set is small and fixed for a personal
    portfolio, so paired columns keep reads a single row with no joins.
    """

    __tablename__ = "projects"

    title_uz: Mapped[str] = mapped_column(String(255), nullable=False)
    title_en: Mapped[str] = mapped_column(String(255), nullable=False)

    description_uz: Mapped[str] = mapped_column(Text, nullable=False)
    description_en: Mapped[str] = mapped_column(Text, nullable=False)

    # Free-form technology/category tags stored as a JSON array. JSON keeps the
    # tag set flexible without a join table; the portfolio never filters by tag.
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Manual sort position. Indexed on its own to serve the admin listing, which
    # orders ALL rows (visible + hidden) by display_order without a filter.
    display_order: Mapped[int] = mapped_column(
        default=0, server_default=text("0"), index=True, nullable=False
    )

    is_visible: Mapped[bool] = mapped_column(
        default=True, server_default=text("true"), nullable=False
    )

    __table_args__ = (
        # Public list endpoint: `WHERE is_visible = true ORDER BY display_order`.
        # This composite serves both the filter and the sort in one index scan. A
        # standalone index on is_visible would be redundant — it is already the
        # leading column here — so we deliberately omit one.
        Index("ix_projects_visible_order", "is_visible", "display_order"),
    )
