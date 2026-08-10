"""Declarative base and shared model mixins."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Without an explicit naming convention, PostgreSQL invents names for indexes, unique
# constraints, and foreign keys. Those auto-generated names differ between databases and are
# not reproducible, so Alembic autogenerate produces migrations that can create a constraint
# it can never drop by name. Fixing the convention up front makes migrations reversible.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for every ORM model in the application."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """UUID primary keys instead of auto-incrementing integers.

    Sequential integer IDs leak information: ``/users/3`` tells a visitor the system has very
    few users, and ``/users/4`` is a guessable neighbour. UUIDs also let a client generate an
    ID before the row exists, which matters once resume uploads are created optimistically.

    The cost is 16 bytes instead of 4 and slightly worse index locality. Irrelevant at our size.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )


class TimestampMixin:
    """Creation and update timestamps, maintained by the database.

    ``server_default`` and ``onupdate`` mean the values are set by PostgreSQL, not by Python.
    That keeps them correct even for rows written by a migration or by hand in psql, and
    avoids clock skew between application replicas.

    All timestamps are timezone-aware and stored as UTC. Naive datetimes in a database are a
    reliable source of bugs the moment anything crosses a timezone.
    """

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
