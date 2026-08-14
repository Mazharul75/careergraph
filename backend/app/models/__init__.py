"""ORM models.

Every model must be imported here. Alembic's autogenerate compares ``Base.metadata`` against
the live database, and a model that was never imported is not in the metadata — so autogenerate
would cheerfully emit a migration that drops the table it doesn't know about.
"""

from app.db.base import Base
from app.models.job import Job, JobSkill
from app.models.refresh_token import RefreshToken
from app.models.resume import ParseStatus, Resume
from app.models.skill import Skill, SkillAlias, SkillCategory
from app.models.skill_edge import SkillEdge
from app.models.user import User, UserRole
from app.models.user_skill import SkillSource, SkillStatus, UserSkill

__all__ = [
    "Base",
    "Job",
    "JobSkill",
    "ParseStatus",
    "RefreshToken",
    "Resume",
    "Skill",
    "SkillAlias",
    "SkillCategory",
    "SkillEdge",
    "SkillSource",
    "SkillStatus",
    "User",
    "UserRole",
    "UserSkill",
]
