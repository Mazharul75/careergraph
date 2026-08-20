"use client";

/**
 * The skill graph, browsable.
 *
 * Its job is to make one claim self-evident: skills are not a flat list. Everything else in
 * the product consumes this structure invisibly — the ordered plan, the inferred
 * prerequisites, the "fastest way in" chain — and a person who has seen the picture once
 * understands all of it afterwards.
 *
 * Filtering by category rather than paginating, because a graph cut into pages stops being a
 * graph: the edges that leave the page are exactly the interesting ones.
 */

import { useMemo, useState } from "react";

import { SkillGraph } from "@/components/SkillGraph";
import { Badge, Button, Card, PageHeader, Spinner } from "@/components/ui";
import { useSkillGraph, useSkillProfile } from "@/lib/queries";

const CATEGORIES = [
  { value: "all", label: "Everything" },
  { value: "language", label: "Languages" },
  { value: "framework", label: "Frameworks" },
  { value: "database", label: "Databases" },
  { value: "infrastructure", label: "Infrastructure" },
  { value: "data_ml", label: "Data & ML" },
  { value: "tool", label: "Tools" },
  { value: "concept", label: "Concepts" },
];

export default function ExplorePage() {
  const { data: graph, isLoading } = useSkillGraph();
  const { data: profile } = useSkillProfile();
  const [category, setCategory] = useState("all");

  const held = useMemo(
    () => new Set(profile?.confirmed.map((e) => e.skill.id) ?? []),
    [profile],
  );
  const learning = useMemo(
    () => new Set(profile?.learning.map((e) => e.skill.id) ?? []),
    [profile],
  );

  const visible = useMemo(() => {
    if (!graph) return { skills: [], edges: [] };
    if (category === "all") return graph;

    const skills = graph.skills.filter((s) => s.category === category);
    const ids = new Set(skills.map((s) => s.id));
    // Keep only edges whose *both* ends survive the filter. A half-anchored arrow points at
    // nothing and reads as a rendering bug rather than a hidden node.
    const edges = graph.edges.filter(
      (e) => ids.has(e.prerequisite_id) && ids.has(e.skill_id),
    );
    return { skills, edges };
  }, [graph, category]);

  return (
    <>
      <PageHeader
        title="Skill graph"
        description="Every skill in the vocabulary, positioned by how deep its prerequisites run. Arrows point from what you need first to what it unlocks."
        action={
          graph ? (
            <Badge>
              {graph.skills.length} skills · {graph.edges.length} edges
            </Badge>
          ) : undefined
        }
      />

      <div className="mb-5 flex flex-wrap gap-2">
        {CATEGORIES.map((option) => (
          <Button
            key={option.value}
            size="sm"
            variant={category === option.value ? "primary" : "secondary"}
            onClick={() => setCategory(option.value)}
          >
            {option.label}
          </Button>
        ))}
      </div>

      <Card className="p-5">
        {isLoading ? (
          <Spinner label="Loading the graph" />
        ) : visible.skills.length > 0 ? (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-4 text-xs text-[var(--color-muted)]">
              <span className="flex items-center gap-1.5">
                <span className="size-3 rounded border border-[var(--color-positive)] bg-[var(--color-positive-soft)]" />
                you have this
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-3 rounded border border-[var(--color-brand)] bg-[var(--color-brand-soft)]" />
                learning
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-3 rounded border border-[var(--color-line)] bg-[var(--color-surface)]" />
                not yet
              </span>
              <span className="ml-auto">Click any skill for its plan.</span>
            </div>

            <SkillGraph
              skills={visible.skills}
              edges={visible.edges}
              held={held}
              learning={learning}
            />
          </>
        ) : (
          <p className="text-sm text-[var(--color-muted)]">
            No skills in this category.
          </p>
        )}
      </Card>

      <p className="mt-4 text-xs leading-relaxed text-[var(--color-muted)]">
        Position on the horizontal axis is dependency depth, computed as the{" "}
        <strong className="font-semibold">longest</strong> path to each skill — a skill is only
        learnable once every chain feeding into it is finished, so its true position is set by
        its deepest prerequisite, not its shallowest.
      </p>
    </>
  );
}
