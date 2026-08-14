"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import type { SkillGap } from "@/lib/types";

/**
 * Skill-gap radar: what the job needs, versus what you have.
 *
 * Grouped by **category** rather than plotting individual skills, and that choice matters. A
 * radar with twenty spokes is unreadable, and jobs rarely require the same twenty skills, so
 * per-skill axes would also make two jobs impossible to compare. Six stable category axes are
 * legible and comparable.
 *
 * The value on each axis is importance-weighted coverage, matching how the headline score is
 * computed — a chart that disagreed with the number beside it would be worse than no chart.
 */

const CATEGORY_LABELS: Record<string, string> = {
  language: "Languages",
  framework: "Frameworks",
  database: "Databases",
  infrastructure: "Infrastructure",
  data_ml: "Data & ML",
  tool: "Tools",
  concept: "Concepts",
};

export interface RadarDatum {
  category: string;
  /** 0-100 */
  coverage: number;
  have: number;
  need: number;
}

export function buildRadarData(
  matched: SkillGap[],
  missing: SkillGap[],
  categoryOf: (skillId: string) => string | undefined,
): RadarDatum[] {
  const buckets = new Map<string, { have: number; need: number; haveWeight: number; total: number }>();

  const add = (gap: SkillGap, held: boolean) => {
    const category = categoryOf(gap.skill_id) ?? "concept";
    const bucket = buckets.get(category) ?? { have: 0, need: 0, haveWeight: 0, total: 0 };
    bucket.need += 1;
    bucket.total += gap.importance;
    if (held) {
      bucket.have += 1;
      bucket.haveWeight += gap.importance;
    }
    buckets.set(category, bucket);
  };

  matched.forEach((gap) => add(gap, true));
  missing.forEach((gap) => add(gap, false));

  return [...buckets.entries()]
    .map(([category, bucket]) => ({
      category: CATEGORY_LABELS[category] ?? category,
      coverage: bucket.total ? Math.round((bucket.haveWeight / bucket.total) * 100) : 0,
      have: bucket.have,
      need: bucket.need,
    }))
    .sort((a, b) => a.category.localeCompare(b.category));
}

export function SkillRadar({ data }: { data: RadarDatum[] }) {
  // Three axes is the minimum for a radar to read as a shape rather than a line or a triangle
  // collapsed to a point. Below that, a plain list communicates more.
  if (data.length < 3) {
    return (
      <ul className="space-y-2">
        {data.map((datum) => (
          <li key={datum.category} className="flex items-center justify-between text-sm">
            <span>{datum.category}</span>
            <span className="text-[var(--color-muted)]">
              {datum.have}/{datum.need} · {datum.coverage}%
            </span>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="72%">
          <PolarGrid stroke="var(--color-line)" />
          <PolarAngleAxis
            dataKey="category"
            tick={{ fill: "var(--color-muted)", fontSize: 12 }}
          />
          <PolarRadiusAxis domain={[0, 100]} tick={{ fill: "var(--color-muted)", fontSize: 10 }} />
          <Radar
            name="Coverage"
            dataKey="coverage"
            stroke="var(--color-brand)"
            fill="var(--color-brand)"
            fillOpacity={0.28}
          />
          <Tooltip
            // Recharts types the formatter value as a broad union, so narrow it here rather
            // than asserting — a category with no data legitimately yields undefined.
            formatter={(value, _name, item) => {
              const datum = item?.payload as RadarDatum | undefined;
              if (typeof value !== "number" || !datum) return ["—", "Coverage"];
              return [`${value}% · ${datum.have} of ${datum.need} skills`, "Coverage"];
            }}
            contentStyle={{
              borderRadius: 8,
              border: "1px solid var(--color-line)",
              fontSize: 13,
            }}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
