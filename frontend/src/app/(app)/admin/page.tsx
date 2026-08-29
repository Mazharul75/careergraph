"use client";

/**
 * Operator console.
 *
 * Guarded twice, and both guards matter. The client check below decides what to *render*;
 * the server's `require_role(ADMIN)` on the whole admin router decides what is actually
 * allowed. Client-side role checks are a usability feature — they stop a non-admin seeing a
 * broken page — and never a security control, because anyone can edit the JavaScript.
 */

import { Badge, Button, Card, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import {
  useAdminUsers,
  useAdminVerifyEmail,
  useSetUserActive,
  useSetUserRole,
  useSystemStats,
} from "@/lib/queries";
import type { AdminUser, UserRole } from "@/lib/types";

function Stat({ label, value, tone }: { label: string; value: number; tone?: "warn" }) {
  return (
    <Card className="p-4">
      <p
        className={`text-2xl font-semibold tabular-nums ${
          tone === "warn" && value > 0 ? "text-[var(--color-warn)]" : ""
        }`}
      >
        {value}
      </p>
      <p className="mt-0.5 text-xs text-[var(--color-muted)]">{label}</p>
    </Card>
  );
}

const ROLE_TONE: Record<UserRole, "neutral" | "brand" | "danger"> = {
  job_seeker: "neutral",
  recruiter: "brand",
  admin: "danger",
};

function UserRow({ row, selfId }: { row: AdminUser; selfId: string | undefined }) {
  const setActive = useSetUserActive();
  const setRole = useSetUserRole();
  const verifyEmail = useAdminVerifyEmail();
  const isSelf = row.id === selfId;
  const busy = setActive.isPending || setRole.isPending || verifyEmail.isPending;
  // Verifying only ever means something for a password account — a Google sign-in is
  // already verified the moment Google itself vouches for the address.
  const needsManualVerification = !row.email_verified && row.has_password;

  return (
    <tr className="border-t border-[var(--color-line)]">
      <td className="py-3 pr-4">
        <p className="text-sm font-medium">{row.full_name ?? "—"}</p>
        <p className="text-xs text-[var(--color-muted)]">{row.email}</p>
      </td>
      <td className="py-3 pr-4">
        <Badge tone={ROLE_TONE[row.role]}>{row.role.replace("_", " ")}</Badge>
      </td>
      <td className="py-3 pr-4 text-sm tabular-nums text-[var(--color-muted)]">
        {row.skill_count} skills · {row.resume_count} resumes
      </td>
      <td className="py-3 pr-4">
        <div className="flex flex-wrap gap-1.5">
          {row.is_active ? (
            <Badge tone="positive">active</Badge>
          ) : (
            <Badge tone="danger">suspended</Badge>
          )}
          {needsManualVerification ? (
            <Badge tone="warn">email unconfirmed</Badge>
          ) : null}
        </div>
      </td>
      <td className="py-3">
        <div className="flex flex-wrap justify-end gap-2">
          {needsManualVerification ? (
            <Button
              size="sm"
              variant="secondary"
              disabled={busy}
              onClick={() => verifyEmail.mutate(row.id)}
              title="Their email provider may not be able to deliver a real link — vouch for them directly."
            >
              Verify email
            </Button>
          ) : null}

          <select
            aria-label={`Role for ${row.email}`}
            className="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] px-2 py-1 text-xs"
            value={row.role}
            disabled={busy}
            onChange={(event) =>
              setRole.mutate({ userId: row.id, role: event.target.value as UserRole })
            }
          >
            <option value="job_seeker">job seeker</option>
            <option value="recruiter">recruiter</option>
            <option value="admin">admin</option>
          </select>

          {/* Suspending yourself is refused by the server too; hiding the button spares the
              operator a pointless error. */}
          {!isSelf ? (
            <Button
              size="sm"
              variant={row.is_active ? "secondary" : "primary"}
              disabled={busy}
              onClick={() => setActive.mutate({ userId: row.id, isActive: !row.is_active })}
            >
              {row.is_active ? "Suspend" : "Restore"}
            </Button>
          ) : (
            <span className="self-center text-xs text-[var(--color-muted)]">you</span>
          )}
        </div>
      </td>
    </tr>
  );
}

export default function AdminPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const { data: stats, isLoading: statsLoading } = useSystemStats(isAdmin);
  const { data: users, isLoading: usersLoading } = useAdminUsers(isAdmin);

  if (!isAdmin) {
    return (
      <>
        <PageHeader title="Admin" />
        <EmptyState
          title="Administrators only"
          description="This console is limited to admin accounts. The server enforces this regardless of what the interface shows."
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Operations"
        description="Fleet health and account administration."
      />

      {statsLoading ? (
        <Card className="p-6">
          <Spinner label="Loading system stats" />
        </Card>
      ) : stats ? (
        <section className="space-y-4">
          <h2 className="text-sm font-semibold">People</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="total users" value={stats.total_users} />
            <Stat label="job seekers" value={stats.job_seekers} />
            <Stat label="recruiters" value={stats.recruiters} />
            <Stat label="suspended" value={stats.inactive_users} tone="warn" />
          </div>

          <h2 className="pt-2 text-sm font-semibold">Content and pipeline</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="jobs" value={stats.total_jobs} />
            <Stat label="public postings" value={stats.public_jobs} />
            <Stat label="resumes" value={stats.total_resumes} />
            <Stat label="parses in flight" value={stats.resumes_pending} />
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="failed parses" value={stats.resumes_failed} tone="warn" />
            <Stat label="active goals" value={stats.active_goals} />
            <Stat label="goals reached" value={stats.achieved_goals} />
            <Stat label="admins" value={stats.admins} />
          </div>
        </section>
      ) : null}

      <section className="mt-8">
        <h2 className="text-sm font-semibold">Accounts</h2>
        {usersLoading ? (
          <Card className="mt-3 p-6">
            <Spinner label="Loading accounts" />
          </Card>
        ) : (
          <Card className="mt-3 overflow-x-auto p-5">
            <table className="w-full min-w-[42rem] text-left">
              <thead>
                <tr className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
                  <th className="pb-2 font-medium">User</th>
                  <th className="pb-2 font-medium">Role</th>
                  <th className="pb-2 font-medium">Activity</th>
                  <th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users?.map((row) => (
                  <UserRow key={row.id} row={row} selfId={user?.id} />
                ))}
              </tbody>
            </table>
          </Card>
        )}
        <p className="mt-3 text-xs text-[var(--color-muted)]">
          Suspending an account takes effect on its next request — the API re-reads active
          status on every call, so an unexpired token stops working immediately.
        </p>
        <p className="mt-1.5 text-xs text-[var(--color-muted)]">
          &ldquo;Email unconfirmed&rdquo; usually means the address is not the one this
          deployment&apos;s email provider is allowed to deliver to yet (common on a
          sandbox sender before a domain is verified) — &ldquo;Verify email&rdquo; unblocks
          that person without waiting on a link that will never arrive.
        </p>
      </section>
    </>
  );
}
