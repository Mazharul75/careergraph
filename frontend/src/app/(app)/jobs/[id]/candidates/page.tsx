"use client";

/**
 * The recruiter view that did not exist before: candidates ranked against your posting.
 *
 * Every row carries its reasoning — the skills matched and the skills missing — for the same
 * reason the job-seeker match does. An unexplained "78%" is not something a person will act
 * on when the decision affects someone's career.
 */

import Link from "next/link";
import { use } from "react";

import { Badge, Button, Card, EmptyState, Meter, PageHeader, Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useCandidates, useJob } from "@/lib/queries";
import type { RankedCandidate } from "@/lib/types";

function CandidateCard({ candidate, rank }: { candidate: RankedCandidate; rank: number }) {
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[var(--color-canvas)] text-sm font-semibold text-[var(--color-muted)]">
            {rank}
          </span>
          <div className="min-w-0">
            <p className="truncate font-medium">{candidate.full_name ?? "Anonymous candidate"}</p>
            <p className="text-xs text-[var(--color-muted)]">
              {candidate.matched.length} of {candidate.matched.length + candidate.missing.length}{" "}
              required skills
              {candidate.has_resume ? "" : " · no resume analysed yet"}
            </p>
          </div>
        </div>
        <p className="text-2xl font-semibold tabular-nums">
          {candidate.score.toFixed(1)}
          <span className="text-sm text-[var(--color-muted)]">%</span>
        </p>
      </div>

      <div className="mt-4">
        <Meter value={candidate.score} />
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            Has
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {candidate.matched.length > 0 ? (
              candidate.matched.slice(0, 8).map((s) => (
                <Badge key={s.skill_id} tone="positive">
                  {s.canonical_name}
                </Badge>
              ))
            ) : (
              <span className="text-sm text-[var(--color-muted)]">None of the named skills</span>
            )}
          </div>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            Missing
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {candidate.missing.length > 0 ? (
              candidate.missing.slice(0, 8).map((s) => (
                <Badge key={s.skill_id} tone="warn">
                  {s.canonical_name}
                </Badge>
              ))
            ) : (
              <span className="text-sm text-[var(--color-muted)]">Nothing — full coverage</span>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

export default function CandidatesPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { user } = useAuth();
  const canRank = user?.role === "recruiter" || user?.role === "admin";

  const { data: job } = useJob(id);
  const { data: candidates, isLoading, error } = useCandidates(id, canRank);

  if (!canRank) {
    return (
      <>
        <PageHeader title="Candidates" />
        <EmptyState
          title="Recruiter accounts only"
          description="Ranking candidates is available to recruiters for postings they created."
          action={
            <Link href="/jobs">
              <Button size="sm">Back to jobs</Button>
            </Link>
          }
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Ranked candidates"
        description={
          job
            ? `Everyone on the platform, scored against "${job.title}" with the reasoning shown.`
            : "Scored against your posting."
        }
        action={
          <Link href={`/jobs/${id}`}>
            <Button variant="secondary" size="sm">
              Back to posting
            </Button>
          </Link>
        }
      />

      {isLoading ? (
        <Card className="p-6">
          <Spinner label="Scoring candidates" />
        </Card>
      ) : error ? (
        <EmptyState
          title="Not available"
          description="You can only rank candidates for a posting you created."
          action={
            <Link href="/jobs">
              <Button size="sm">Back to jobs</Button>
            </Link>
          }
        />
      ) : candidates && candidates.length > 0 ? (
        <div className="space-y-4">
          {candidates.map((candidate, index) => (
            <CandidateCard key={candidate.user_id} candidate={candidate} rank={index + 1} />
          ))}
          <p className="text-xs text-[var(--color-muted)]">
            Candidates with no overlap at all are omitted — a list of 0% rows teaches nothing.
          </p>
        </div>
      ) : (
        <EmptyState
          title="No candidates yet"
          description="Nobody on the platform shares any of the skills this posting asks for."
        />
      )}
    </>
  );
}
