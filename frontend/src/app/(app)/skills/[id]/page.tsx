"use client";

/**
 * One skill, and how to reach it.
 *
 * This page exists because the learning path on a job answers "what order for this role?"
 * while people also arrive with a narrower question: "I want to learn Kubernetes — where do
 * I actually start?" The graph already knows; it just had no page.
 *
 * Two different answers are shown deliberately. The **plan** is everything still missing,
 * topologically ordered. The **shortest route** is the single cheapest chain from something
 * you already know to the target, weighted by difficulty rather than hop count — the fastest
 * way in, as opposed to the complete picture.
 */

import Link from "next/link";
import { use } from "react";

import { Badge, Button, Card, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { useSkillCatalogue, useSkillPath, useSkillProfile, useStartLearning } from "@/lib/queries";

const DIFFICULTY_LABEL = ["", "beginner", "easy", "moderate", "hard", "expert"];

export default function SkillDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: catalogue } = useSkillCatalogue();
  const { data: profile } = useSkillProfile();
  const { data: path, isLoading, error } = useSkillPath(id);
  const startLearning = useStartLearning();

  const skill = catalogue?.find((s) => s.id === id);

  const held = profile?.confirmed.some((e) => e.skill.id === id) ?? false;
  const learning = profile?.learning.some((e) => e.skill.id === id) ?? false;

  if (error) {
    return (
      <>
        <PageHeader title="Skill" />
        <EmptyState
          title="Skill not found"
          description="That skill is not in the vocabulary."
          action={
            <Link href="/skills">
              <Button size="sm">Back to skills</Button>
            </Link>
          }
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={skill?.canonical_name ?? "Skill"}
        description={
          skill
            ? `${skill.category.replace("_", " ")} · ${DIFFICULTY_LABEL[skill.difficulty] ?? "moderate"} to learn`
            : undefined
        }
        action={
          held ? (
            <Badge tone="positive">You have this</Badge>
          ) : learning ? (
            <Badge tone="brand">Learning</Badge>
          ) : (
            <Button
              size="sm"
              disabled={startLearning.isPending}
              onClick={() => startLearning.mutate(id)}
            >
              {startLearning.isPending ? "Adding…" : "Start learning"}
            </Button>
          )
        }
      />

      {isLoading ? (
        <Card className="p-6">
          <Spinner label="Reading the graph" />
        </Card>
      ) : path ? (
        <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
          <Card className="p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Everything still missing, in order</h2>
              <Badge>{path.step_count} steps</Badge>
            </div>

            {path.steps.length > 0 ? (
              <ol className="mt-5 space-y-2">
                {path.steps.map((step) => (
                  <li key={step.skill_id} className="flex items-center gap-3">
                    <span className="tabular-figures flex size-7 shrink-0 items-center justify-center rounded-lg bg-[var(--color-brand-soft)] text-xs font-semibold text-[var(--color-brand)]">
                      {step.order}
                    </span>
                    <Link
                      href={`/skills/${step.skill_id}`}
                      className="min-w-0 flex-1 rounded-lg border border-[var(--color-line)] px-3 py-2 text-sm transition hover:border-[var(--color-line-strong)] hover:bg-[var(--color-canvas)]"
                    >
                      <span className="font-medium">{step.canonical_name}</span>
                      {!step.directly_required ? (
                        <span className="ml-2 text-xs text-[var(--color-muted)]">
                          prerequisite
                        </span>
                      ) : null}
                    </Link>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="mt-4 text-sm text-[var(--color-muted)]">
                Nothing to learn — you already have this skill and everything it depends on.
              </p>
            )}

            {path.total_effort > 0 ? (
              <p className="mt-5 border-t border-[var(--color-line)] pt-4 text-xs text-[var(--color-muted)]">
                Total effort {path.total_effort}, summed from each skill&apos;s difficulty rating.
              </p>
            ) : null}
          </Card>

          <div className="space-y-6">
            <Card className="p-5">
              <h2 className="text-sm font-semibold">Fastest way in</h2>
              <p className="mt-1 text-xs text-[var(--color-muted)]">
                The cheapest single chain from what you already know, weighted by difficulty —
                not simply the fewest hops.
              </p>
              {path.shortest_route.length > 0 ? (
                <div className="mt-4 flex flex-wrap items-center gap-1.5">
                  {path.shortest_route.map((name, index) => (
                    <span key={name} className="flex items-center gap-1.5">
                      {index > 0 ? (
                        <span className="text-[var(--color-faint)]">→</span>
                      ) : null}
                      <span className="rounded-lg bg-[var(--color-canvas)] px-2.5 py-1 text-sm font-medium">
                        {name}
                      </span>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="mt-3 text-sm text-[var(--color-muted)]">
                  Already reachable — no prerequisites stand in the way.
                </p>
              )}
            </Card>

            {path.unreachable.length > 0 ? (
              <Card className="p-5">
                <h2 className="text-sm font-semibold">Not reachable</h2>
                <p className="mt-1 text-xs text-[var(--color-muted)]">
                  These have no path from your current profile — usually a gap in the seeded
                  graph rather than something impossible.
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {path.unreachable.map((name) => (
                    <Badge key={name} tone="warn">
                      {name}
                    </Badge>
                  ))}
                </div>
              </Card>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}
