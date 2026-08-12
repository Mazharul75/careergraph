"""Resume model."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ParseStatus(enum.StrEnum):
    """Lifecycle of a resume's background parse.

    Stored in the database rather than read from Celery's result backend. The status is
    application state the user asks about through the API, not an implementation detail of the
    queue — and keeping it here means the queue can be swapped, or a result expire, without
    the user's resume appearing to vanish.
    """

    PENDING = "pending"  # accepted, queued, not yet picked up
    PROCESSING = "processing"  # a worker has claimed it
    COMPLETE = "complete"
    FAILED = "failed"


class Resume(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "resumes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[ParseStatus] = mapped_column(
        Enum(
            ParseStatus,
            name="parse_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=ParseStatus.PENDING.value,
        index=True,
    )

    # The uploaded bytes, held only until parsing succeeds, then cleared.
    #
    # `deferred` matters: Postgres stores large values out-of-line (TOAST), but a plain
    # `SELECT *` still pulls them back. Deferring means listing a user's ten resumes reads ten
    # rows of metadata rather than ten megabytes of PDF; the column loads only when touched.
    file_data: Mapped[bytes | None] = deferred(
        mapped_column(LargeBinary, nullable=True),
    )

    extracted_text: Mapped[str | None] = deferred(mapped_column(Text, nullable=True))

    # Populated only when status is FAILED. Holds a short, user-safe reason — never a
    # traceback, which would leak file paths and library versions.
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    @property
    def is_terminal(self) -> bool:
        """True once the resume will not change state again without being re-queued."""
        return self.status in (ParseStatus.COMPLETE, ParseStatus.FAILED)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Resume id={self.id} user={self.user_id} status={self.status.value}>"
