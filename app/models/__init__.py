"""Central registry of SQLAlchemy models.

One module per model in this package; import everything here so the tables
are registered on ``Base.metadata`` and picked up by Alembic autogenerate:

    __all__ = ["Base"]
"""

from app.core.database import Base  # noqa: F401

__all__ = ["Base"]
