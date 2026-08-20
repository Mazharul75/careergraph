"use client";

/**
 * The skill graph, drawn.
 *
 * Every other view renders the graph's *output* — an ordered list. This one renders the graph
 * itself, because "skills have prerequisites" is a claim people believe far faster when they
 * can see the arrows.
 *
 * Laid out by **depth**, not by force simulation. A force-directed layout looks impressive and
 * communicates nothing: node positions carry no meaning and shuffle on every render. Here the
 * x-axis *is* dependency depth — how many prerequisites deep a skill sits — so left-to-right
 * reads as learning order, which is the one thing the picture needs to say.
 *
 * Plain SVG, no charting dependency. The whole layout is about forty lines of arithmetic, and
 * a library would add weight plus a second opinion about how graphs should look.
 */

import Link from "next/link";
import { useMemo } from "react";

import type { Skill } from "@/lib/types";

export interface GraphEdge {
  prerequisite_id: string;
  skill_id: string;
}

interface Positioned {
  skill: Skill;
  depth: number;
  row: number;
}

const COL_WIDTH = 190;
const ROW_HEIGHT = 54;
const NODE_WIDTH = 152;
const NODE_HEIGHT = 34;

/**
 * Longest-path depth for each node.
 *
 * Longest rather than shortest on purpose: a skill is only learnable once *every* chain
 * feeding it is done, so its true position is set by its deepest prerequisite. Shortest-path
 * depth would draw Kubernetes as though Linux alone unlocked it.
 */
function computeDepths(skills: Skill[], edges: GraphEdge[]): Map<string, number> {
  const prerequisites = new Map<string, string[]>();
  for (const edge of edges) {
    const list = prerequisites.get(edge.skill_id) ?? [];
    list.push(edge.prerequisite_id);
    prerequisites.set(edge.skill_id, list);
  }

  const depths = new Map<string, number>();
  const visiting = new Set<string>();

  const depthOf = (id: string): number => {
    const cached = depths.get(id);
    if (cached !== undefined) return cached;
    // The seed data is validated as acyclic at migration time, but a guard here means a bad
    // edge degrades the picture instead of hanging the browser.
    if (visiting.has(id)) return 0;

    visiting.add(id);
    const parents = prerequisites.get(id) ?? [];
    const depth = parents.length === 0 ? 0 : Math.max(...parents.map(depthOf)) + 1;
    visiting.delete(id);

    depths.set(id, depth);
    return depth;
  };

  for (const skill of skills) depthOf(skill.id);
  return depths;
}

export function SkillGraph({
  skills,
  edges,
  held,
  learning,
}: {
  skills: Skill[];
  edges: GraphEdge[];
  held: Set<string>;
  learning: Set<string>;
}) {
  const { nodes, width, height, positions } = useMemo(() => {
    const depths = computeDepths(skills, edges);

    const byDepth = new Map<number, Skill[]>();
    for (const skill of skills) {
      const depth = depths.get(skill.id) ?? 0;
      const column = byDepth.get(depth) ?? [];
      column.push(skill);
      byDepth.set(depth, column);
    }

    const placed: Positioned[] = [];
    let tallest = 0;
    for (const [depth, column] of [...byDepth.entries()].sort((a, b) => a[0] - b[0])) {
      column.sort((a, b) => a.canonical_name.localeCompare(b.canonical_name));
      column.forEach((skill, row) => placed.push({ skill, depth, row }));
      tallest = Math.max(tallest, column.length);
    }

    const pos = new Map<string, { x: number; y: number }>();
    for (const node of placed) {
      pos.set(node.skill.id, {
        x: node.depth * COL_WIDTH + NODE_WIDTH / 2 + 16,
        y: node.row * ROW_HEIGHT + NODE_HEIGHT / 2 + 40,
      });
    }

    const maxDepth = Math.max(...placed.map((n) => n.depth), 0);
    return {
      nodes: placed,
      positions: pos,
      width: (maxDepth + 1) * COL_WIDTH + 40,
      height: tallest * ROW_HEIGHT + 70,
    };
  }, [skills, edges]);

  if (skills.length === 0) return null;

  return (
    <div className="overflow-x-auto">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Dependency graph of ${skills.length} skills`}
        className="min-w-full"
      >
        <defs>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-line-strong)" />
          </marker>
        </defs>

        {/* Edges first, so nodes paint over them rather than being crossed by lines. */}
        <g>
          {edges.map((edge) => {
            const from = positions.get(edge.prerequisite_id);
            const to = positions.get(edge.skill_id);
            if (!from || !to) return null;
            const startX = from.x + NODE_WIDTH / 2;
            const endX = to.x - NODE_WIDTH / 2;
            if (endX <= startX) return null;
            const midX = (startX + endX) / 2;
            return (
              <path
                key={`${edge.prerequisite_id}-${edge.skill_id}`}
                d={`M ${startX} ${from.y} C ${midX} ${from.y}, ${midX} ${to.y}, ${endX} ${to.y}`}
                fill="none"
                stroke="var(--color-line-strong)"
                strokeWidth="1.25"
                markerEnd="url(#arrow)"
                opacity={0.75}
              />
            );
          })}
        </g>

        <g>
          {nodes.map(({ skill }) => {
            const p = positions.get(skill.id);
            if (!p) return null;
            const isHeld = held.has(skill.id);
            const isLearning = learning.has(skill.id);
            const fill = isHeld
              ? "var(--color-positive-soft)"
              : isLearning
                ? "var(--color-brand-soft)"
                : "var(--color-surface)";
            const stroke = isHeld
              ? "var(--color-positive)"
              : isLearning
                ? "var(--color-brand)"
                : "var(--color-line)";

            return (
              <Link key={skill.id} href={`/skills/${skill.id}`}>
                <g className="cursor-pointer">
                  <rect
                    x={p.x - NODE_WIDTH / 2}
                    y={p.y - NODE_HEIGHT / 2}
                    width={NODE_WIDTH}
                    height={NODE_HEIGHT}
                    rx={8}
                    fill={fill}
                    stroke={stroke}
                    strokeWidth={isHeld || isLearning ? 1.5 : 1}
                  />
                  <text
                    x={p.x}
                    y={p.y + 4}
                    textAnchor="middle"
                    className="fill-[var(--color-ink)] text-[11px] font-medium"
                  >
                    {skill.canonical_name.length > 18
                      ? `${skill.canonical_name.slice(0, 17)}…`
                      : skill.canonical_name}
                  </text>
                </g>
              </Link>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
