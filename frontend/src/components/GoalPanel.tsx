"use client";

/**
 * The journey, made visible.
 *
 * This component is the answer to the question the product previously could not answer:
 * "what changed because of what I did?" It shows three numbers that only mean something
 * together — where you started, where you are, and how far the bar still runs — and puts the
 * two actions that move them directly next to the gaps they apply to.
 *
 * The deliberate detail: "Start learning" does **not** move the score, and the UI says so out
 * loud. Hiding that would make the number feel arbitrary the first time someone clicked and
 * nothing happened.
 */

import Link from "next/link";
import { useState } from "react";

import { Badge, Button, Card, Meter, Spinner } from "@/components/ui";
import { useAbandonGoal, useAchieveGoal, useMarkLearned, useStartLearning } from "@/lib/queries";
import type { GoalProgress, GoalSkillGap } from "@/lib/types";

function DeltaBadge({ delta }: { delta: number }) {
  if (delta === 0) {
    return <span className="text-xs text-[var(--color-muted)]">no change yet</span>;
  }
  const positive = delta > 0;
  return (
    <span
      className={`text-xs font-semibold ${
        positive ? "text-[var(--color-positive)]" : "text-[var(--color-danger)]"
      }`}
    >
      {positive ? "+" : ""}
      {delta.toFixed(1)} since you started
    </span>
  );
}

function GapRow({
  gap,
  onStart,
  onFinish,
  busy,
}: {
  gap: GoalSkillGap;
  onStart: (id: string) => void;
  onFinish: (id: string) => void;
  busy: boolean;
}) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-lg px-2 py-2 transition hover:bg-[var(--color-canvas)]">
      <span className="flex min-w-0 items-center gap-2">
        <span className="truncate text-sm">{gap.canonical_name}</span>
        {gap.importance >= 4 ? <Badge tone="warn">key</Badge> : null}
        {gap.is_learning ? <Badge tone="brand">learning</Badge> : null}
      </span>

      {gap.is_learning ? (
        <Button size="sm" disabled={busy} onClick={() => onFinish(gap.skill_id)}>
          I&apos;ve learned this
        </Button>
      ) : (
        <Button
          size="sm"
          variant="secondary"
          disabled={busy}
          onClick={() => onStart(gap.skill_id)}
        >
          Start learning
        </Button>
      )}
    </li>
  );
}

export function GoalPanel({ goal }: { goal: GoalProgress }) {
  const startLearning = useStartLearning();
  const markLearned = useMarkLearned();
  const achieve = useAchieveGoal();
  const abandon = useAbandonGoal();
  const [confirmingAbandon, setConfirmingAbandon] = useState(false);

  const busy = startLearning.isPending || markLearned.isPending;
  const inProgress = goal.missing.filter((gap) => gap.is_learning);
  const notStarted = goal.missing.filter((gap) => !gap.is_learning);

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
              Working toward
            </p>
            <h2 className="mt-1 truncate text-xl font-semibold">
              <Link href={`/jobs/${goal.job.id}`} className="hover:underline">
                {goal.job.title}
              </Link>
            </h2>
            {goal.job.company ? (
              <p className="text-sm text-[var(--color-muted)]">{goal.job.company}</p>
            ) : null}
          </div>

          <div className="text-right">
            <p className="text-3xl font-semibold tabular-nums">
              {goal.current_score.toFixed(1)}
              <span className="text-base text-[var(--color-muted)]">%</span>
            </p>
            <DeltaBadge delta={goal.delta} />
          </div>
        </div>

        <div className="mt-5">
          <Meter value={goal.readiness} tone={goal.is_achievable_now ? "positive" : "brand"} />
          <div className="mt-2 flex justify-between text-xs text-[var(--color-muted)]">
            <span>started at {goal.baseline_score.toFixed(1)}%</span>
            <span>{goal.readiness.toFixed(0)}% ready</span>
          </div>
        </div>

        {!goal.semantic_available ? (
          <p className="mt-3 text-xs text-[var(--color-muted)]">
            Scoring on skills alone for now — the semantic comparison appears once your resume
            has been analysed.
          </p>
        ) : null}

        <div className="mt-5 flex flex-wrap gap-2">
          {goal.is_achievable_now ? (
            <Button
              disabled={achieve.isPending}
              onClick={() => achieve.mutate(goal.id)}
            >
              {achieve.isPending ? "Saving…" : "Mark this goal reached"}
            </Button>
          ) : null}

          {confirmingAbandon ? (
            <>
              <Button
                variant="secondary"
                size="sm"
                disabled={abandon.isPending}
                onClick={() => abandon.mutate(goal.id)}
              >
                Yes, choose a different target
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmingAbandon(false)}>
                Cancel
              </Button>
            </>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => setConfirmingAbandon(true)}>
              Change target
            </Button>
          )}
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">Currently learning</h3>
            <span className="text-xs text-[var(--color-muted)]">{inProgress.length}</span>
          </div>
          {inProgress.length > 0 ? (
            <>
              <ul className="mt-3 space-y-1">
                {inProgress.map((gap) => (
                  <GapRow
                    key={gap.skill_id}
                    gap={gap}
                    busy={busy}
                    onStart={(id) => startLearning.mutate(id)}
                    onFinish={(id) => markLearned.mutate(id)}
                  />
                ))}
              </ul>
              <p className="mt-3 text-xs text-[var(--color-muted)]">
                These do not count toward your score yet. Marking one learned is what moves the
                number.
              </p>
            </>
          ) : (
            <p className="mt-2 text-sm text-[var(--color-muted)]">
              Nothing in progress. Pick a gap on the right to start.
            </p>
          )}
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">Still missing</h3>
            <span className="text-xs text-[var(--color-muted)]">{notStarted.length}</span>
          </div>
          {notStarted.length > 0 ? (
            <ul className="mt-3 space-y-1">
              {notStarted.slice(0, 8).map((gap) => (
                <GapRow
                  key={gap.skill_id}
                  gap={gap}
                  busy={busy}
                  onStart={(id) => startLearning.mutate(id)}
                  onFinish={(id) => markLearned.mutate(id)}
                />
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-[var(--color-muted)]">
              Nothing missing — you cover every skill this role asks for.
            </p>
          )}
          <Link href={`/jobs/${goal.job.id}`} className="mt-4 inline-block">
            <Button variant="secondary" size="sm">
              See the ordered plan
            </Button>
          </Link>
        </Card>
      </div>

      {achieve.isError ? (
        <p className="text-sm text-[var(--color-danger)]">
          You have not reached the threshold yet — keep going.
        </p>
      ) : null}
    </div>
  );
}

export function GoalPanelSkeleton() {
  return (
    <Card className="p-6">
      <Spinner label="Loading your goal" />
    </Card>
  );
}
