"""ORM models, re-exported for convenient imports and Alembic autogenerate.

Importing this package registers every model on ``Base.metadata``, which is how
Alembic's ``--autogenerate`` discovers the full schema. Each model subclasses
``app.db.base.Base``.
"""

from app.models.contact import ContactMessage
from app.models.media import MediaItem, MediaPlacement, MediaType
from app.models.project import Project

__all__ = ["ContactMessage", "MediaItem", "MediaPlacement", "MediaType", "Project"]
