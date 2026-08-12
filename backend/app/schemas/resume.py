"""Resume request and response contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.resume import ParseStatus


class ResumeSummary(BaseModel):
    """Metadata only — deliberately excludes the file bytes and the extracted text.

    This is what the upload endpoint returns and what list views are built from, so neither can
    accidentally serialise a multi-megabyte PDF into a JSON response.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    status: ParseStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ResumeText(BaseModel):
    """The parsed result. Only meaningful once status is ``complete``."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ParseStatus
    extracted_text: str | None = Field(
        default=None,
        description="Null until parsing completes.",
    )
    character_count: int = 0
