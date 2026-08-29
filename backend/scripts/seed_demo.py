"""Populate a deployment with realistic demo data, end to end.

**Why this drives the HTTP API rather than the database.** Seeding straight into Postgres
would be faster and completely useless as a test: it would skip auth, skip validation, skip
the Celery queue, and skip skill extraction — every part of the system worth demonstrating.
Going through the API means that when this script finishes successfully, the whole pipeline
has just been proven to work on that deployment.

It is also why the same script works against localhost and against Render with no changes.

What it creates:
  * 1 recruiter, who owns every public posting (so candidate ranking has an owner)
  * 5 job seekers with distinct, deliberately uneven skill profiles
  * A parsed PDF resume for each seeker, uploaded and extracted for real
  * 6 public job postings spanning backend, devops, data, frontend, ML and junior roles
  * An active career goal for the lead demo account, with two skills already in progress

Usage:
    uv run python scripts/seed_demo.py
    uv run python scripts/seed_demo.py --base-url https://careergraph-api-f9n2.onrender.com

Re-runnable: every account gets a unique suffix, so nothing collides with a previous run.
Registration is rate limited to 20/hour per IP (ADR-0011), and this creates 6 accounts — so
roughly three runs per hour against the same deployment before the limiter says no.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The user's own shell is cmd.exe (see CLAUDE.md), whose default codepage is cp1252 — it
# cannot encode "→" or "✓" and raises UnicodeEncodeError partway through printing the
# summary, after every real piece of work below has already succeeded. Reconfiguring stdout
# to UTF-8 fixes this regardless of the terminal's active codepage, on every platform.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEMO_PASSWORD = "CareerGraph-Demo-2026"  # noqa: S105 - throwaway accounts on a demo deployment


# --------------------------------------------------------------------------------------
# A minimal PDF, hand-assembled
# --------------------------------------------------------------------------------------


def make_pdf(lines: list[str]) -> bytes:
    """Build a valid single-page PDF containing `lines`.

    Hand-assembled rather than pulled from reportlab, which would be a multi-megabyte
    dependency used by nothing else. Byte offsets for the xref table are computed as objects
    are appended, so the file is structurally valid rather than relying on the parser being
    forgiving about broken cross-reference tables.
    """
    parts = []
    y = 720
    for line in lines:
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        parts.append(f"BT /F1 11 Tf 60 {y} Td ({escaped}) Tj ET")
        y -= 18
    stream = "\n".join(parts)

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref_at}\n%%EOF\n".encode()
    return bytes(out)


# --------------------------------------------------------------------------------------
# Demo content
# --------------------------------------------------------------------------------------


@dataclass
class Seeker:
    handle: str
    name: str
    headline: str
    resume: list[str]
    email: str = ""
    token: str = ""
    resume_id: str = ""


# Profiles are deliberately uneven. If everyone knew the same things, candidate ranking would
# return a flat list and prove nothing — the demo needs a visible spread of scores.
SEEKERS: list[Seeker] = [
    Seeker(
        handle="ada",
        name="Ada Rahman",
        headline="Strong backend, no infrastructure",
        resume=[
            "Ada Rahman - Backend Developer",
            "Built REST services in Python using FastAPI and Flask.",
            "Designed normalised schemas in PostgreSQL and wrote complex SQL queries.",
            "Used Git daily for version control and code review.",
            "Comfortable on Linux for day-to-day development work.",
            "Wrote unit and integration tests with pytest.",
        ],
    ),
    Seeker(
        handle="samir",
        name="Samir Chowdhury",
        headline="Infrastructure heavy, lighter on application code",
        resume=[
            "Samir Chowdhury - Platform Engineer",
            "Operated production Kubernetes clusters and wrote Helm charts.",
            "Containerised services with Docker and built CI/CD pipelines.",
            "Managed infrastructure on AWS using Terraform.",
            "Administered Linux servers and troubleshot networking issues.",
            "Maintained Redis caches and monitored system health.",
        ],
    ),
    Seeker(
        handle="nadia",
        name="Nadia Islam",
        headline="Data and ML background",
        resume=[
            "Nadia Islam - Data Scientist",
            "Analysed datasets with Python, pandas and NumPy.",
            "Trained models using scikit-learn and PyTorch.",
            "Wrote SQL against PostgreSQL for feature extraction.",
            "Built dashboards and reported findings to stakeholders.",
            "Familiar with Git and Jupyter notebooks.",
        ],
    ),
    Seeker(
        handle="rafi",
        name="Rafi Hasan",
        headline="Frontend specialist",
        resume=[
            "Rafi Hasan - Frontend Engineer",
            "Built single-page applications with React and TypeScript.",
            "Used Next.js for server-side rendering and routing.",
            "Styled interfaces with CSS and Tailwind.",
            "Consumed REST APIs and handled authentication flows.",
            "Version control with Git, deployments through CI/CD.",
        ],
    ),
    Seeker(
        handle="tanvir",
        name="Tanvir Ahmed",
        headline="Early career - the account with the most to learn",
        resume=[
            "Tanvir Ahmed - Computer Science Graduate",
            "Coursework in algorithms, data structures and databases.",
            "Wrote small projects in Python and Java.",
            "Basic SQL and an introduction to Git.",
            "Eager to learn backend development and cloud infrastructure.",
        ],
    ),
]

JOBS: list[dict[str, str]] = [
    {
        "title": "Backend Engineer",
        "company": "Northwind Labs",
        "location": "Remote",
        "description": (
            "We are hiring a Backend Engineer to design and build REST APIs with Python and "
            "FastAPI. You will model data in PostgreSQL, use Redis for caching and queues, "
            "and containerise services with Docker. Experience with CI/CD, Git and Linux is "
            "expected. Familiarity with AWS and Kubernetes is a strong plus. You will write "
            "tests with pytest and take part in code review."
        ),
    },
    {
        "title": "DevOps Engineer",
        "company": "Cirrus Systems",
        "location": "Dhaka, Bangladesh",
        "description": (
            "Join our platform team to run production Kubernetes clusters on AWS. You will "
            "manage infrastructure as code with Terraform, build and maintain CI/CD "
            "pipelines, and containerise workloads with Docker. Deep Linux and networking "
            "knowledge is essential. You will operate PostgreSQL and Redis in production and "
            "automate deployments using Git-based workflows."
        ),
    },
    {
        "title": "Full Stack Developer",
        "company": "Meridian Digital",
        "location": "Hybrid - Dhaka",
        "description": (
            "Build features end to end. On the frontend you will work with React, TypeScript "
            "and Next.js. On the backend you will write Python services with FastAPI backed "
            "by PostgreSQL. You will use Docker locally, Git for version control, and deploy "
            "through CI/CD. An eye for REST API design and clean HTML and CSS is important."
        ),
    },
    {
        "title": "Machine Learning Engineer",
        "company": "Aurora AI",
        "location": "Remote",
        "description": (
            "Work on production machine learning systems. You will use Python with pandas, "
            "NumPy, scikit-learn and PyTorch to train and evaluate models. You will serve "
            "models behind REST APIs built with FastAPI, store features in PostgreSQL, and "
            "package everything with Docker. Understanding of NLP and embeddings is valuable. "
            "Linux, Git and CI/CD are part of daily work."
        ),
    },
    {
        "title": "Junior Software Engineer",
        "company": "Bluepeak",
        "location": "Dhaka, Bangladesh",
        "description": (
            "A role for someone early in their career. You should be comfortable writing "
            "Python, understand basic SQL and relational databases, and know your way around "
            "Git. We will teach you the rest: Linux fundamentals, Docker, testing with pytest "
            "and REST API design. Curiosity matters more than a long list of technologies."
        ),
    },
    {
        "title": "Site Reliability Engineer",
        "company": "Helix Cloud",
        "location": "Remote",
        "description": (
            "Keep large systems running. You will work with Kubernetes, Docker and Terraform "
            "on AWS, build observability into services, and improve CI/CD reliability. Strong "
            "Linux administration and networking skills are required. You will tune "
            "PostgreSQL and Redis under load and write automation in Python and Bash."
        ),
    },
]


# --------------------------------------------------------------------------------------
# API helpers
# --------------------------------------------------------------------------------------


@dataclass
class Api:
    client: httpx.Client
    created: list[str] = field(default_factory=list)

    def register(self, email: str, name: str, role: str = "job_seeker") -> str:
        response = self.client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": DEMO_PASSWORD, "full_name": name, "role": role},
        )
        if response.status_code == 429:
            raise SystemExit(
                "Rate limited on registration (20/hour per IP, see ADR-0011).\n"
                "Wait an hour, or run against a different deployment."
            )
        if response.status_code not in (201, 409):
            raise SystemExit(f"register failed for {email}: {response.status_code} {response.text}")

        if response.status_code == 201:
            # New accounts start unverified and cannot log in yet. The dev-mode token this
            # deployment hands back (local/ci only — see Settings.exposes_dev_verification_tokens)
            # is what lets this script complete the real /verify-email flow instead of a
            # backdoor that skips it. A 409 means the account survived a previous run of this
            # script and is already verified, so there is nothing to redeem here.
            dev_token = response.json().get("dev_verification_token")
            if not dev_token:
                raise SystemExit(
                    f"No dev_verification_token in the register response for {email}.\n"
                    "This deployment's ENVIRONMENT is not 'local' or 'ci', so this script "
                    "cannot verify the account for you — confirm it from the email that was "
                    "actually sent, or set RESEND_API_KEY so one goes out."
                )
            verify = self.client.post("/api/v1/auth/verify-email", json={"token": dev_token})
            if verify.status_code != 200:
                raise SystemExit(f"verify failed for {email}: {verify.status_code} {verify.text}")

        login = self.client.post(
            "/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD}
        )
        if login.status_code != 200:
            raise SystemExit(f"login failed for {email}: {login.status_code} {login.text}")
        return str(login.json()["access_token"])

    def auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


def wait_for_parse(api: Api, token: str, resume_id: str, timeout: float = 90.0) -> str:
    """Poll until the resume reaches a terminal state.

    The upload returns 202 immediately — that is the whole point of the queue — so the script
    has to wait exactly as the UI does. On a cold free-tier instance the first parse also pays
    for the worker waking up, hence the generous timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = api.client.get(f"/api/v1/resumes/{resume_id}", headers=api.auth(token))
        if response.status_code == 200:
            status = response.json()["status"]
            if status in ("complete", "failed"):
                return str(status)
        time.sleep(2.0)
    return "timeout"


# --------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--skip-resumes",
        action="store_true",
        help="Create accounts and jobs but no resume uploads (much faster).",
    )
    args = parser.parse_args()

    suffix = uuid.uuid4().hex[:6]

    with httpx.Client(base_url=args.base_url, timeout=120.0) as client:
        api = Api(client)

        health = client.get("/health")
        if health.status_code != 200:
            print(f"API at {args.base_url} is not healthy ({health.status_code}).", file=sys.stderr)
            return 1
        print(f"Seeding {args.base_url}\n")

        # --- Recruiter --------------------------------------------------------------
        recruiter_email = f"recruiter.{suffix}@careergraph.demo"
        recruiter_token = api.register(recruiter_email, "Priya Sen", role="recruiter")
        print(f"  recruiter   {recruiter_email}")

        # --- Jobs -------------------------------------------------------------------
        # Public, and owned by the recruiter, so candidate ranking has somebody to rank for.
        job_ids: list[tuple[str, str]] = []
        for job in JOBS:
            response = client.post(
                "/api/v1/jobs",
                json={**job, "is_public": True},
                headers=api.auth(recruiter_token),
            )
            if response.status_code != 201:
                raise SystemExit(f"job failed: {response.status_code} {response.text}")
            job_ids.append((str(response.json()["id"]), job["title"]))
        print(f"  jobs        {len(job_ids)} public postings\n")

        # --- Job seekers ------------------------------------------------------------
        for seeker in SEEKERS:
            seeker.email = f"{seeker.handle}.{suffix}@careergraph.demo"
            seeker.token = api.register(seeker.email, seeker.name)

            if not args.skip_resumes:
                pdf = make_pdf(seeker.resume)
                upload = client.post(
                    "/api/v1/resumes",
                    files={"file": (f"{seeker.handle}.pdf", pdf, "application/pdf")},
                    headers=api.auth(seeker.token),
                )
                if upload.status_code != 202:
                    raise SystemExit(f"upload failed: {upload.status_code} {upload.text}")
                seeker.resume_id = str(upload.json()["id"])

            print(f"  seeker      {seeker.email:<44} {seeker.headline}")

        # --- Wait for the queue -----------------------------------------------------
        if not args.skip_resumes:
            print("\n  waiting for the worker to parse resumes…")
            for seeker in SEEKERS:
                status = wait_for_parse(api, seeker.token, seeker.resume_id)
                profile = client.get("/api/v1/skills/me", headers=api.auth(seeker.token)).json()
                print(
                    f"    {seeker.handle:<8} {status:<9} "
                    f"{profile['total_suggested']} skills extracted"
                )

            # Confirm everyone's suggestions so the demo starts from a realistic profile
            # rather than one where nothing counts yet.
            for seeker in SEEKERS:
                client.post("/api/v1/skills/me/confirm-all", headers=api.auth(seeker.token))

        # --- A goal in progress for the lead account --------------------------------
        lead = SEEKERS[0]
        backend_job = job_ids[0][0]
        goal = client.post(
            "/api/v1/goals", json={"job_id": backend_job}, headers=api.auth(lead.token)
        )
        if goal.status_code == 201:
            body = goal.json()
            for gap in body["missing"][:2]:
                client.post(
                    "/api/v1/skills/me/learning",
                    json={"skill_id": gap["skill_id"]},
                    headers=api.auth(lead.token),
                )
            print(
                f"\n  goal        {lead.handle} targeting 'Backend Engineer' "
                f"at {body['baseline_score']}% with 2 skills in progress"
            )

        # --- What to do next --------------------------------------------------------
        print("\n" + "=" * 78)
        print("SIGN IN WITH ANY OF THESE".center(78))
        print("=" * 78)
        print(f"  password (all accounts):  {DEMO_PASSWORD}\n")
        print(f"  {'RECRUITER':<12} {recruiter_email}")
        print(f"  {'':12} → open a job, then 'View candidates' to see the ranking\n")
        for seeker in SEEKERS:
            print(f"  {'JOB SEEKER':<12} {seeker.email}")
        print(f"\n  {'START HERE':<12} {SEEKERS[0].email}")
        print(f"  {'':12} → already has a goal in progress; mark a skill learned")
        print(f"  {'':12}   and watch the score move.")
        print("=" * 78)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
