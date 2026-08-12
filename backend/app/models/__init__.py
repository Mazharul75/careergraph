"""ORM models.

Every model must be imported here. Alembic's autogenerate compares ``Base.metadata`` against
the live database, and a model that was never imported is not in the metadata — so autogenerate
would cheerfully emit a migration that drops the table it doesn't know about.
"""

from app.db.base import Base
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole

__all__ = ["Base", "RefreshToken", "User", "UserRole"]
