"use client";

import { Badge, Card, EmptyState, Spinner } from "@/components/ui";
import type { LearningPath, PathStep } from "@/lib/types";

/**
 * The learning path, drawn as an ordered spine.
 *
 * A vertical numbered sequence rather than a node-link diagram, deliberately. A force-directed
 * graph looks impressive in a screenshot and is worse at the one job this has: telling someone
 * what to do next. The ordering is the product, so the ordering is what the layout expresses.
 *
 * Inferred steps — prerequisites the job description never mentioned — are marked, because
 * "the posting asked for this" and "you need this first, even though nobody said so" are
 * different claims and a user should be able to tell them apart.
 */

const DIFFICULTY_LABEL = ["", "a weekend", "a week or two", "a few weeks", "a month or two", "months"];

function StepCard({ step, isLast }: { step: PathStep; isLast: boolean }) {
  return (
    <li className="relative flex gap-4 pb-6 last:pb-0">
      {/* The connector line is what makes this read as a sequence rather than a list. */}
      {!isLast ? (
        <span aria-hidden className="absolute left-4 top-9 h-full w-px bg-[var(--color-line)]" />
      ) : null}

      <span
        aria-hidden
        className={`relative z-10 flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${
          step.directly_required
            ? "bg-[var(--color-brand)] text-white"
            : "border border-[var(--color-line)] bg-[var(--color-surface)] text-[var(--color-muted)]"
        }`}
      >
        {step.order}
      </span>

      <div className="min-w-0 flex-1 pt-0.5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold">{step.canonical_name}</h3>
          {step.directly_required ? (
            <Badge tone="brand">Required by this job</Badge>
          ) : (
            <Badge>Prerequisite</Badge>
          )}
        </div>

        <p className="mt-1 text-xs text-[var(--color-muted)]">
          Roughly {DIFFICULTY_LABEL[step.difficulty] ?? "a while"} of study
          {step.unlocked_by.length > 0 ? <> · builds on {step.unlocked_by.join(", ")}</> : null}
        </p>
      </div>
    </li>
  );
}

export function LearningPathView({
  path,
  isLoading,
}: {
  path: LearningPath | undefined;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <Card className="p-5">
        <Spinner label="Working out your path…" />
      </Card>
    );
  }

  if (!path) return null;

  if (path.step_count === 0) {
    return (
      <EmptyState
        title="You already have every skill this job needs"
        description="Nothing to learn here. Try a more demanding posting to find your next gap."
      />
    );
  }

  const inferred = path.steps.filter((s) => !s.directly_required).length;

  return (
    <Card className="p-5">
      <div className="mb-5 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Your learning path</h2>
        <p className="text-xs text-[var(--color-muted)]">
          {path.step_count} {path.step_count === 1 ? "step" : "steps"} · effort {path.total_effort}
        </p>
      </div>

      {inferred > 0 ? (
        <p className="mb-5 rounded-lg bg-[var(--color-canvas)] px-3.5 py-2.5 text-xs text-[var(--color-muted)]">
          {inferred} {inferred === 1 ? "step is" : "steps are"} not mentioned in the job description.
          They are prerequisites — you need them before the skills the posting does ask for.
        </p>
      ) : null}

      <ol>
        {path.steps.map((step, index) => (
          <StepCard key={step.skill_id} step={step} isLast={index === path.steps.length - 1} />
        ))}
      </ol>

      {path.unreachable.length > 0 ? (
        <p className="mt-4 text-xs text-[var(--color-warn)]">
          {path.unreachable.length} required skill(s) are not in our vocabulary yet, so they are
          not planned for.
        </p>
      ) : null}
    </Card>
  );
}
