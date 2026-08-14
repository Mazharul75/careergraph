"use client";

import Link from "next/link";

import { ResumeUpload } from "@/components/ResumeUpload";
import { Badge, Button, Card, PageHeader, Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useJobs, useSkillProfile } from "@/lib/queries";

export default function DashboardPage() {
  const { user } = useAuth();
  const { data: profile, isLoading: profileLoading } = useSkillProfile();
  const { data: jobs } = useJobs();

  const firstName = user?.full_name?.split(" ")[0];

  return (
    <>
      <PageHeader
        title={firstName ? `Welcome back, ${firstName}` : "Dashboard"}
        description="Upload a resume, review the skills we found, then measure yourself against a job."
      />

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <ResumeUpload />

        <div className="space-y-6">
          <Card className="p-5">
            <h2 className="text-sm font-semibold">Your skill profile</h2>
            {profileLoading ? (
              <div className="mt-4">
                <Spinner />
              </div>
            ) : (
              <>
                <div className="mt-4 flex gap-6">
                  <div>
                    <p className="text-2xl font-semibold">{profile?.total_confirmed ?? 0}</p>
                    <p className="text-xs text-[var(--color-muted)]">confirmed</p>
                  </div>
                  <div>
                    <p className="text-2xl font-semibold">{profile?.total_suggested ?? 0}</p>
                    <p className="text-xs text-[var(--color-muted)]">awaiting review</p>
                  </div>
                </div>

                {profile && profile.total_suggested > 0 ? (
                  <p className="mt-3 text-xs text-[var(--color-muted)]">
                    Extraction is not perfect. Reviewing these makes every score more accurate.
                  </p>
                ) : null}

                <Link href="/skills" className="mt-4 inline-block">
                  <Button variant="secondary" size="sm">
                    {profile && profile.total_suggested > 0 ? "Review suggestions" : "Manage skills"}
                  </Button>
                </Link>
              </>
            )}
          </Card>

          <Card className="p-5">
            <h2 className="text-sm font-semibold">Jobs you are tracking</h2>
            {jobs && jobs.length > 0 ? (
              <ul className="mt-3 space-y-2">
                {jobs.slice(0, 4).map((job) => (
                  <li key={job.id}>
                    <Link
                      href={`/jobs/${job.id}`}
                      className="flex items-center justify-between rounded-lg px-2 py-1.5 text-sm transition hover:bg-[var(--color-canvas)]"
                    >
                      <span className="truncate">{job.title}</span>
                      {job.is_public ? <Badge tone="brand">Public</Badge> : null}
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-[var(--color-muted)]">
                None yet. Add a posting to see where you stand.
              </p>
            )}
            <Link href="/jobs" className="mt-4 inline-block">
              <Button variant="secondary" size="sm">
                Go to jobs
              </Button>
            </Link>
          </Card>
        </div>
      </div>
    </>
  );
}
