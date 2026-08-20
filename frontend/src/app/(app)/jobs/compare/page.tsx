"use client";

/**
 * Compare several jobs at once.
 *
 * The single-job page answers "how do I score against this?" That is the wrong question when
 * someone is deciding *which* role to chase — for that you need the scores side by side, and
 * more usefully, the skills that several roles want in common. A skill three targets all
 * require is worth learning first no matter which one you end up applying for.
 *
 * Each job's score is fetched with the existing per-job hook rather than a new bulk endpoint.
 * React Query dedupes and caches by key, so opening this page after visiting a job costs
 * nothing extra, and there is no second scoring path to keep consistent with the first.
 */

import Link from "next/link";
import { useMemo, useState } from "react";

import { Badge, Button, Card, EmptyState, Meter, PageHeader, Spinner } from "@/components/ui";
import { useJobs, useMatch } from "@/lib/queries";
import type { JobSummary } from "@/lib/types";

const MAX_COMPARE = 3;

function JobColumn({ job }: { job: JobSummary }) {
  const { data: match, isLoading } = useMatch(job.id);

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link href={`/jobs/${job.id}`} className="font-medium hover:underline">
            {job.title}
          </Link>
          {job.company ? (
            <p className="truncate text-xs text-[var(--color-muted)]">{job.company}</p>
          ) : null}
        </div>
        {match ? (
          <span className="tabular-figures text-xl font-bold">{match.score.toFixed(0)}%</span>
        ) : null}
      </div>

      {isLoading ? (
        <div className="mt-4">
          <Spinner label="Scoring" />
        </div>
      ) : match ? (
        <>
          <div className="mt-3">
            <Meter value={match.score} />
          </div>

          <dl className="mt-4 space-y-1.5 text-xs">
            <div className="flex justify-between">
              <dt className="text-[var(--color-muted)]">Skills you have</dt>
              <dd className="tabular-figures font-medium">
                {match.matched.length}/{match.total_required}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[var(--color-muted)]">Still missing</dt>
              <dd className="tabular-figures font-medium">{match.missing.length}</dd>
            </div>
            {!match.semantic_available ? (
              <p className="pt-1 text-[var(--color-muted)]">Skills only — still embedding.</p>
            ) : null}
          </dl>

          <div className="mt-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
              Biggest gaps
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {match.missing.slice(0, 6).map((gap) => (
                <Badge key={gap.skill_id} tone="warn">
                  {gap.canonical_name}
                </Badge>
              ))}
              {match.missing.length === 0 ? (
                <span className="text-xs text-[var(--color-muted)]">Full coverage.</span>
              ) : null}
            </div>
          </div>
        </>
      ) : null}
    </Card>
  );
}

/**
 * Skills wanted by more than one of the selected roles.
 *
 * The most actionable output on the page: learning one of these advances every target at
 * once, which is a materially better use of a week than a skill only one job asked for.
 */
function SharedGaps({ jobs }: { jobs: JobSummary[] }) {
  const first = useMatch(jobs[0]?.id ?? "");
  const second = useMatch(jobs[1]?.id ?? "");
  const third = useMatch(jobs[2]?.id ?? "");

  const shared = useMemo(() => {
    const results = [first.data, second.data, third.data].filter(
      (m): m is NonNullable<typeof m> => Boolean(m),
    );
    if (results.length < 2) return [];

    const counts = new Map<string, { name: string; count: number }>();
    for (const result of results) {
      for (const gap of result.missing) {
        const entry = counts.get(gap.skill_id) ?? { name: gap.canonical_name, count: 0 };
        entry.count += 1;
        counts.set(gap.skill_id, entry);
      }
    }
    return [...counts.entries()]
      .filter(([, v]) => v.count > 1)
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, 12);
  }, [first.data, second.data, third.data]);

  if (shared.length === 0) return null;

  return (
    <Card className="mt-6 p-5">
      <h2 className="text-sm font-semibold">Wanted by more than one of these</h2>
      <p className="mt-1 text-xs text-[var(--color-muted)]">
        Learning one of these moves you closer to several targets at once — the best return on
        a week of study.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        {shared.map(([id, { name, count }]) => (
          <Link
            key={id}
            href={`/skills/${id}`}
            className="flex items-center gap-2 rounded-lg border border-[var(--color-line)] px-3 py-1.5 text-sm transition hover:border-[var(--color-brand)] hover:bg-[var(--color-brand-soft)]"
          >
            {name}
            <span className="tabular-figures rounded-full bg-[var(--color-accent-soft)] px-1.5 text-xs font-semibold text-[var(--color-accent)]">
              {count}
            </span>
          </Link>
        ))}
      </div>
    </Card>
  );
}

export default function ComparePage() {
  const { data: jobs, isLoading } = useJobs();
  const [selected, setSelected] = useState<string[]>([]);

  const chosen = useMemo(
    () => (jobs ?? []).filter((job) => selected.includes(job.id)),
    [jobs, selected],
  );

  const toggle = (id: string) =>
    setSelected((current) =>
      current.includes(id)
        ? current.filter((x) => x !== id)
        : current.length >= MAX_COMPARE
          ? current
          : [...current, id],
    );

  if (isLoading) {
    return (
      <Card className="p-6">
        <Spinner />
      </Card>
    );
  }

  if (!jobs || jobs.length < 2) {
    return (
      <>
        <PageHeader title="Compare roles" />
        <EmptyState
          title="Add at least two jobs"
          description="Comparison needs more than one target. Paste another posting and come back."
          action={
            <Link href="/jobs">
              <Button size="sm">Go to jobs</Button>
            </Link>
          }
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Compare roles"
        description={`Pick up to ${MAX_COMPARE} jobs and see where you stand against each — and what they want in common.`}
      />

      <Card className="p-5">
        <h2 className="text-sm font-semibold">Choose roles</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {jobs.map((job) => {
            const active = selected.includes(job.id);
            const full = selected.length >= MAX_COMPARE && !active;
            return (
              <button
                key={job.id}
                type="button"
                disabled={full}
                onClick={() => toggle(job.id)}
                className={`rounded-lg border px-3 py-1.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-40 ${
                  active
                    ? "border-[var(--color-brand)] bg-[var(--color-brand-soft)] text-[var(--color-brand)]"
                    : "border-[var(--color-line)] hover:bg-[var(--color-canvas)]"
                }`}
              >
                {job.title}
              </button>
            );
          })}
        </div>
      </Card>

      {chosen.length > 0 ? (
        <>
          <div className="mt-6 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {chosen.map((job) => (
              <JobColumn key={job.id} job={job} />
            ))}
          </div>
          <SharedGaps jobs={chosen} />
        </>
      ) : (
        <p className="mt-6 text-sm text-[var(--color-muted)]">
          Select a role above to begin.
        </p>
      )}
    </>
  );
}
