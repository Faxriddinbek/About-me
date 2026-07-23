"""SQLAlchemy declarative base with shared, audited columns.

Every model inherits ``id`` plus server-generated ``created_at`` / ``updated_at``
timestamps. Using server-side defaults (``func.now()``) makes the database the
single source of truth for timing, so timestamps stay correct regardless of
which process or timezone wrote the row.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base carrying the columns common to all tables.

    ``Base`` itself is not mapped to a table (it has no ``__tablename__``); its
    columns are inherited by concrete models defined in ``app.models``.
    """

    id: Mapped[int] = mapped_column(primary_key=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
