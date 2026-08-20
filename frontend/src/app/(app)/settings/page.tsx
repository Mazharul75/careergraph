"use client";

/**
 * Account settings.
 *
 * Read-mostly on purpose. The things a user genuinely needs visibility of here are their
 * identity, their role, and what the system is holding on their behalf — not a wall of
 * toggles invented to fill the page. Anything destructive routes through a deliberate
 * confirmation rather than sitting one click away.
 */

import Link from "next/link";

import { Badge, Button, Card, PageHeader, Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useAchievements, useCurrentGoal, useResumes, useSkillProfile } from "@/lib/queries";
import type { UserRole } from "@/lib/types";

const ROLE_COPY: Record<UserRole, { label: string; body: string }> = {
  job_seeker: {
    label: "Job seeker",
    body: "You can upload resumes, track a target role, and follow a learning plan.",
  },
  recruiter: {
    label: "Recruiter",
    body: "You can publish public postings and rank candidates against roles you created.",
  },
  admin: {
    label: "Administrator",
    body: "You have access to the operations console: fleet stats and account administration.",
  },
};

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-line)] px-5 py-4 first:border-t-0">
      <span className="text-sm text-[var(--color-muted)]">{label}</span>
      <span className="text-sm font-medium">{children}</span>
    </div>
  );
}

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const { data: profile } = useSkillProfile();
  const { data: resumes } = useResumes();
  const { data: goal } = useCurrentGoal();
  const { data: achievements } = useAchievements();

  if (!user) {
    return (
      <Card className="p-6">
        <Spinner />
      </Card>
    );
  }

  const role = ROLE_COPY[user.role];

  return (
    <>
      <PageHeader
        title="Settings"
        description="Your account, and what CareerGraph is holding for you."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-6">
          <Card>
            <div className="px-5 py-4">
              <h2 className="text-sm font-semibold">Account</h2>
            </div>
            <Row label="Email">{user.email}</Row>
            <Row label="Name">{user.full_name ?? "—"}</Row>
            <Row label="Role">
              <Badge tone={user.role === "admin" ? "danger" : "brand"}>{role.label}</Badge>
            </Row>
            <Row label="Status">
              {user.is_active ? (
                <Badge tone="positive">Active</Badge>
              ) : (
                <Badge tone="danger">Suspended</Badge>
              )}
            </Row>
            <p className="border-t border-[var(--color-line)] px-5 py-4 text-xs leading-relaxed text-[var(--color-muted)]">
              {role.body}
            </p>
          </Card>

          <Card className="p-5">
            <h2 className="text-sm font-semibold">Session</h2>
            <p className="mt-1.5 text-xs leading-relaxed text-[var(--color-muted)]">
              Access tokens last fifteen minutes and refresh silently in the background. Signing
              out revokes the refresh token immediately, on this device and any other that
              shares it.
            </p>
            <Button variant="secondary" size="sm" className="mt-4" onClick={() => void logout()}>
              Sign out
            </Button>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <div className="px-5 py-4">
              <h2 className="text-sm font-semibold">Your data</h2>
            </div>
            <Row label="Confirmed skills">{profile?.total_confirmed ?? 0}</Row>
            <Row label="Currently learning">{profile?.total_learning ?? 0}</Row>
            <Row label="Awaiting review">{profile?.total_suggested ?? 0}</Row>
            <Row label="Resumes uploaded">{resumes?.length ?? 0}</Row>
            <Row label="Active goal">
              {goal ? (
                <Link href={`/jobs/${goal.job.id}`} className="hover:underline">
                  {goal.job.title}
                </Link>
              ) : (
                <span className="text-[var(--color-muted)]">None set</span>
              )}
            </Row>
            <Row label="Goals reached">{achievements?.length ?? 0}</Row>
          </Card>

          <Card className="p-5">
            <h2 className="text-sm font-semibold">What we keep</h2>
            <ul className="mt-3 space-y-2.5 text-xs leading-relaxed text-[var(--color-muted)]">
              <li className="flex gap-2.5">
                <span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--color-brand)]" />
                <span>
                  Uploaded files are <strong className="font-semibold">deleted</strong> once their
                  text has been extracted. We keep the text, not the document.
                </span>
              </li>
              <li className="flex gap-2.5">
                <span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--color-brand)]" />
                <span>
                  Recruiters ranking candidates see names, scores and skills — never your resume
                  or your email address.
                </span>
              </li>
              <li className="flex gap-2.5">
                <span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--color-brand)]" />
                <span>
                  Passwords are stored only as an Argon2id hash. No plaintext column exists
                  anywhere in the schema.
                </span>
              </li>
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
