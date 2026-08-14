"use client";

import Link from "next/link";
import { use, useMemo } from "react";

import { LearningPathView } from "@/components/LearningPathView";
import { SkillRadar, buildRadarData } from "@/components/SkillRadar";
import { Alert, Badge, Card, Meter, PageHeader, Spinner } from "@/components/ui";
import { useJob, useLearningPath, useMatch, useSkillCatalogue } from "@/lib/queries";

function scoreTone(score: number): "positive" | "brand" {
  return score >= 70 ? "positive" : "brand";
}

export default function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  // Next 16 delivers route params as a promise; `use` unwraps it in a client component.
  const { id } = use(params);

  const { data: job, isLoading: jobLoading, error } = useJob(id);
  const { data: match, isLoading: matchLoading } = useMatch(id);
  const { data: path, isLoading: pathLoading } = useLearningPath(id);
  const { data: catalogue } = useSkillCatalogue();

  const categoryOf = useMemo(() => {
    const byId = new Map(catalogue?.map((skill) => [skill.id, skill.category]) ?? []);
    return (skillId: string) => byId.get(skillId);
  }, [catalogue]);

  const radar = useMemo(
    () => (match ? buildRadarData(match.matched, match.missing, categoryOf) : []),
    [match, categoryOf],
  );

  if (jobLoading) return <Spinner label="Loading job" />;
  if (error || !job) {
    return (
      <Alert>
        We could not find that job. It may have been deleted, or it belongs to someone else.{" "}
        <Link href="/jobs" className="underline">
          Back to jobs
        </Link>
      </Alert>
    );
  }

  return (
    <>
      <PageHeader
        title={job.title}
        description={[job.company, job.location].filter(Boolean).join(" · ") || undefined}
        action={job.is_public ? <Badge tone="brand">Public posting</Badge> : undefined}
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        <div className="space-y-6">
          {/* --- Score ------------------------------------------------------------- */}
          <Card className="p-5">
            <h2 className="text-sm font-semibold">Match score</h2>

            {matchLoading || !match ? (
              <div className="mt-4">
                <Spinner label="Scoring" />
              </div>
            ) : (
              <>
                <p className="mt-3 text-4xl font-semibold tabular-nums">
                  {match.score.toFixed(0)}
                  <span className="text-lg text-[var(--color-muted)]">/100</span>
                </p>

                <div className="mt-4 space-y-3">
                  <div>
                    <div className="mb-1 flex justify-between text-xs text-[var(--color-muted)]">
                      <span>Skill coverage</span>
                      <span className="tabular-nums">
                        {Math.round(match.skill_coverage * 100)}%
                      </span>
                    </div>
                    <Meter value={match.skill_coverage * 100} tone={scoreTone(match.score)} />
                  </div>

                  <div>
                    <div className="mb-1 flex justify-between text-xs text-[var(--color-muted)]">
                      <span>Semantic similarity</span>
                      <span className="tabular-nums">
                        {match.semantic_available
                          ? `${Math.round(match.semantic_similarity * 100)}%`
                          : "pending"}
                      </span>
                    </div>
                    <Meter value={match.semantic_similarity * 100} />
                  </div>
                </div>

                {!match.semantic_available ? (
                  <p className="mt-3 text-xs text-[var(--color-muted)]">
                    This score is based on skills alone for now. We are still comparing the
                    wording of your resume against the posting — it will update automatically.
                  </p>
                ) : null}

                <p className="mt-3 text-xs text-[var(--color-muted)]">
                  You have {match.matched.length} of {match.total_required} required skills.
                </p>
              </>
            )}
          </Card>

          {/* --- Radar ------------------------------------------------------------- */}
          {radar.length > 0 ? (
            <Card className="p-5">
              <h2 className="text-sm font-semibold">Where the gap is</h2>
              <p className="mt-1 text-xs text-[var(--color-muted)]">
                Coverage by category, weighted by how much this job emphasises each skill.
              </p>
              <div className="mt-3">
                <SkillRadar data={radar} />
              </div>
            </Card>
          ) : null}

          {/* --- Matched / missing -------------------------------------------------- */}
          {match ? (
            <Card className="p-5">
              <h2 className="text-sm font-semibold">Skill breakdown</h2>
              <div className="mt-4 grid gap-5 sm:grid-cols-2">
                <div>
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--color-positive)]">
                    You have ({match.matched.length})
                  </p>
                  <ul className="flex flex-wrap gap-1.5">
                    {match.matched.map((gap) => (
                      <li key={gap.skill_id}>
                        <Badge tone="positive">{gap.canonical_name}</Badge>
                      </li>
                    ))}
                    {match.matched.length === 0 ? (
                      <li className="text-sm text-[var(--color-muted)]">None yet.</li>
                    ) : null}
                  </ul>
                </div>
                <div>
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--color-warn)]">
                    Missing ({match.missing.length})
                  </p>
                  <ul className="flex flex-wrap gap-1.5">
                    {match.missing.map((gap) => (
                      <li key={gap.skill_id}>
                        <Badge tone="warn">{gap.canonical_name}</Badge>
                      </li>
                    ))}
                    {match.missing.length === 0 ? (
                      <li className="text-sm text-[var(--color-muted)]">Nothing missing.</li>
                    ) : null}
                  </ul>
                </div>
              </div>
            </Card>
          ) : null}
        </div>

        {/* --- Learning path -------------------------------------------------------- */}
        <div className="space-y-6">
          <LearningPathView path={path} isLoading={pathLoading} />

          <Card className="p-5">
            <h2 className="text-sm font-semibold">Job description</h2>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-[var(--color-muted)]">
              {job.description}
            </p>
          </Card>
        </div>
      </div>
    </>
  );
}
