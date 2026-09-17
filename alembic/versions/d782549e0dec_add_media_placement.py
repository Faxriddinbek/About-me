"""add media placement

Lets the admin manage the home-page carousel from the same table as the
gallery. Existing rows default to 'gallery', which is what they effectively
were before this column existed.

Revision ID: d782549e0dec
Revises: a97bb8801c0a
Create Date: 2026-08-09 14:19:06.829615

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d782549e0dec"
down_revision: str | None = "a97bb8801c0a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUM_NAME = "media_placement"
ENUM_VALUES = ("hero", "gallery")

# Autogenerate emitted the column without creating the PostgreSQL type first,
# which fails at runtime. The type is created explicitly below, so the column
# definition must be told not to create it a second time.
placement_type = postgresql.ENUM(*ENUM_VALUES, name=ENUM_NAME, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    sa.Enum(*ENUM_VALUES, name=ENUM_NAME).create(bind, checkfirst=True)

    op.add_column(
        "media_items",
        sa.Column(
            "placement",
            placement_type,
            server_default=sa.text("'gallery'"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_media_items_placement_visible_order",
        "media_items",
        ["placement", "is_visible", "display_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_media_items_placement_visible_order", table_name="media_items")
    op.drop_column("media_items", "placement")
    # The type outlives the column, so dropping it here is what makes a
    # downgrade/upgrade cycle repeatable instead of failing on "type exists".
    sa.Enum(*ENUM_VALUES, name=ENUM_NAME).drop(op.get_bind(), checkfirst=True)
