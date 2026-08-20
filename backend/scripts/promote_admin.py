"""Grant or revoke the admin role.

**Why this is a script and not an endpoint.** Admin is the highest privilege in the system,
so there must be no code path that reaches it from the internet. Registration rejects it
(``RegisterRequest.role`` is a ``Literal`` of the other two), and the admin API can only be
called by someone who is already an admin — which leaves a bootstrap problem: nobody can ever
become the first one. This script is the deliberate answer. It needs database credentials,
which means it needs a human with deploy access, which is the correct bar for the privilege.

Usage:
    uv run python scripts/promote_admin.py you@example.com
    uv run python scripts/promote_admin.py you@example.com --revoke
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Python puts the *script's* directory on sys.path, not the working directory, so `app` is
# not importable when this is run as `python scripts/promote_admin.py` from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db.sync_session import SyncSessionFactory
from app.models.user import User, UserRole


def main() -> int:
    parser = argparse.ArgumentParser(description="Grant or revoke the admin role.")
    parser.add_argument("email", help="Email address of an existing account")
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Demote back to job_seeker instead of promoting.",
    )
    args = parser.parse_args()

    email = args.email.strip().lower()
    session = SyncSessionFactory()
    try:
        user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            print(f"No account found for {email}. Register it first.", file=sys.stderr)
            return 1

        if args.revoke:
            admin_count = len(
                session.execute(select(User.id).where(User.role == UserRole.ADMIN)).all()
            )
            if user.role is UserRole.ADMIN and admin_count <= 1:
                # The same rule the API enforces. Applied here too, because a script run at
                # 2am is exactly when someone locks the whole team out.
                print("Refusing: this is the only admin account.", file=sys.stderr)
                return 1
            user.role = UserRole.JOB_SEEKER
            action = "demoted to job_seeker"
        else:
            user.role = UserRole.ADMIN
            action = "promoted to admin"

        session.commit()
        print(f"{email} {action}.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
