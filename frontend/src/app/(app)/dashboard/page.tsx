"use client";

/**
 * The dashboard is now organised around the *goal*, not around the upload form.
 *
 * The previous version showed three equal cards and left the user to work out what to do.
 * This one always answers one question — "what is my next move?" — and the answer changes as
 * the account fills in: upload a resume, then pick a target, then close the gaps.
 */

import Link from "next/link";

import { GoalPanel } from "@/components/GoalPanel";
import { ResumeUpload } from "@/components/ResumeUpload";
import { Badge, Button, Card, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useAchievements, useCurrentGoal, useJobs, useSkillProfile } from "@/lib/queries";

/** The three-step explainer a first-time account sees instead of an empty dashboard. */
function Onboarding({ hasResume, hasSkills }: { hasResume: boolean; hasSkills: boolean }) {
  const steps = [
    {
      title: "Upload your resume",
      body: "We read your skills automatically. Parsing runs in the background.",
      done: hasResume,
    },
    {
      title: "Confirm what we found",
      body: "Extraction is not perfect, and every score depends on this list being right.",
      done: hasSkills,
    },
    {
      title: "Pick a target role",
      body: "Add a job you want. We freeze today's score and track how far you move.",
      done: false,
    },
  ];

  return (
    <Card className="p-6">
      <h2 className="text-sm font-semibold">How this works</h2>
      <ol className="mt-4 space-y-4">
        {steps.map((step, index) => (
          <li key={step.title} className="flex gap-3">
            <span
              className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                step.done
                  ? "bg-[var(--color-positive-soft)] text-[var(--color-positive)]"
                  : "bg-[var(--color-canvas)] text-[var(--color-muted)]"
              }`}
            >
              {step.done ? "✓" : index + 1}
            </span>
            <div>
              <p className="text-sm font-medium">{step.title}</p>
              <p className="text-sm text-[var(--color-muted)]">{step.body}</p>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const { data: profile, isLoading: profileLoading } = useSkillProfile();
  const { data: goal, isLoading: goalLoading } = useCurrentGoal();
  const { data: achievements } = useAchievements();
  const { data: jobs } = useJobs();

  const firstName = user?.full_name?.split(" ")[0];
  const hasSkills = (profile?.total_confirmed ?? 0) + (profile?.total_suggested ?? 0) > 0;
  const hasJobs = (jobs?.length ?? 0) > 0;

  return (
    <>
      <PageHeader
        title={firstName ? `Welcome back, ${firstName}` : "Dashboard"}
        description={
          goal
            ? "Close the gaps below and watch your score climb toward the target."
            : "Upload a resume, then choose the role you are working toward."
        }
        action={
          achievements && achievements.length > 0 ? (
            <Badge tone="positive">
              {achievements.length} goal{achievements.length === 1 ? "" : "s"} reached
            </Badge>
          ) : undefined
        }
      />

      {goalLoading ? (
        <Card className="p-6">
          <Spinner label="Loading your goal" />
        </Card>
      ) : goal ? (
        <div className="space-y-6">
          <GoalPanel goal={goal} />
          <div className="grid gap-6 lg:grid-cols-2">
            <ResumeUpload />
            <Card className="p-5">
              <h3 className="text-sm font-semibold">Your skill profile</h3>
              <div className="mt-4 flex gap-6">
                <div>
                  <p className="text-2xl font-semibold">{profile?.total_confirmed ?? 0}</p>
                  <p className="text-xs text-[var(--color-muted)]">confirmed</p>
                </div>
                <div>
                  <p className="text-2xl font-semibold">{profile?.total_learning ?? 0}</p>
                  <p className="text-xs text-[var(--color-muted)]">learning</p>
                </div>
                <div>
                  <p className="text-2xl font-semibold">{profile?.total_suggested ?? 0}</p>
                  <p className="text-xs text-[var(--color-muted)]">to review</p>
                </div>
              </div>
              <Link href="/skills" className="mt-4 inline-block">
                <Button variant="secondary" size="sm">
                  Manage skills
                </Button>
              </Link>
            </Card>
          </div>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <div className="space-y-6">
            <ResumeUpload />
            {hasJobs ? (
              <Card className="p-5">
                <h3 className="text-sm font-semibold">Choose your target</h3>
                <p className="mt-1 text-sm text-[var(--color-muted)]">
                  Open a job and set it as your goal. We record today&apos;s score so progress
                  is measurable from here.
                </p>
                <ul className="mt-3 space-y-2">
                  {jobs?.slice(0, 4).map((job) => (
                    <li key={job.id}>
                      <Link
                        href={`/jobs/${job.id}`}
                        className="flex items-center justify-between rounded-lg px-2 py-1.5 text-sm transition hover:bg-[var(--color-canvas)]"
                      >
                        <span className="truncate">{job.title}</span>
                        <span className="text-xs text-[var(--color-muted)]">set as goal →</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </Card>
            ) : (
              <EmptyState
                title="No jobs yet"
                description="Paste a job description to see where you stand and set it as your target."
                action={
                  <Link href="/jobs">
                    <Button size="sm">Add a job</Button>
                  </Link>
                }
              />
            )}
          </div>

          {profileLoading ? (
            <Card className="p-5">
              <Spinner />
            </Card>
          ) : (
            <Onboarding hasResume={hasSkills} hasSkills={hasSkills} />
          )}
        </div>
      )}
    </>
  );
}
