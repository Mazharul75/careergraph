"""Orchestration for learning-path generation.

Thin, like every service here: the graph theory lives in ``skill_graph.py`` as pure functions
over plain dataclasses, and this class only fetches inputs and hands them over.
"""

from __future__ import annotations

import uuid

import networkx as nx

from app.models.user import User
from app.models.user_skill import SkillStatus
from app.repositories.protocols import (
    JobRepositoryProtocol,
    SkillRepositoryProtocol,
    UserSkillRepositoryProtocol,
)
from app.services.exceptions import JobNotFoundError, SkillNotFoundError
from app.services.skill_graph import (
    LearningPath,
    build_graph,
    compute_learning_path,
    prerequisite_chain,
)


class LearningPathService:
    def __init__(
        self,
        *,
        jobs: JobRepositoryProtocol,
        skills: SkillRepositoryProtocol,
        user_skills: UserSkillRepositoryProtocol,
    ) -> None:
        self._jobs = jobs
        self._skills = skills
        self._user_skills = user_skills

    async def _known_skill_ids(self, user_id: uuid.UUID) -> frozenset[uuid.UUID]:
        # Confirmed *and* suggested, matching how match scores are computed. A user who has
        # uploaded a resume but not reviewed the suggestions should not be told to learn things
        # their resume already demonstrates.
        entries = await self._user_skills.list_for_user(
            user_id, statuses=(SkillStatus.CONFIRMED, SkillStatus.SUGGESTED)
        )
        return frozenset(entry.skill_id for entry in entries)

    async def _graph(self) -> nx.DiGraph:
        """Load the graph from the database.

        Rebuilt per request: two queries and ~130 edges, a few milliseconds. Caching it would be
        faster but introduces an invalidation problem the moment the vocabulary becomes editable,
        so it is deferred until there is a measurement saying it matters (Phase 6).
        """
        graph_skills = await self._skills.load_graph_skills()
        edges = await self._skills.load_edges()
        return build_graph(graph_skills, edges)

    async def for_job(self, *, user: User, job_id: uuid.UUID) -> LearningPath:
        """The ordered plan that closes this user's gap for this job."""
        job = await self._jobs.get_visible(job_id, user.id)
        if job is None:
            raise JobNotFoundError

        graph = await self._graph()
        known = await self._known_skill_ids(user.id)
        required = frozenset(js.skill_id for js in job.required_skills)

        return compute_learning_path(graph, known=known, required=required)

    async def for_skill(
        self, *, user: User, skill_id: uuid.UUID
    ) -> tuple[LearningPath, tuple[str, ...]]:
        """The plan for one specific skill, plus the single cheapest route to it.

        Two different questions, deliberately answered together: "everything I must learn" and
        "the most direct path", which is what a user asks when they only care about one item.
        """
        if await self._skills.get(skill_id) is None:
            raise SkillNotFoundError

        graph = await self._graph()
        known = await self._known_skill_ids(user.id)

        path = compute_learning_path(graph, known=known, required=frozenset({skill_id}))
        chain = prerequisite_chain(graph, target=skill_id, known=known)
        return path, chain
