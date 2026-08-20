"use client";

import { useMemo, useState } from "react";

import { Badge, Button, Card, EmptyState, PageHeader, Input, Spinner } from "@/components/ui";
import {
  useAddSkill,
  useConfirmAllSkills,
  useSkillCatalogue,
  useSkillProfile,
  useUpdateSkill,
} from "@/lib/queries";
import type { UserSkill } from "@/lib/types";

function SkillRow({ entry, suggested }: { entry: UserSkill; suggested: boolean }) {
  const update = useUpdateSkill();
  return (
    <li className="flex flex-wrap items-center gap-3 border-t border-[var(--color-line)] px-5 py-3 first:border-t-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{entry.skill.canonical_name}</p>
        <p className="text-xs text-[var(--color-muted)]">
          {entry.skill.category.replace("_", " ")}
          {entry.occurrences > 0 ? ` · mentioned ${entry.occurrences} times` : " · added by you"}
        </p>
      </div>

      {suggested ? (
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => update.mutate({ skillId: entry.skill.id, status: "confirmed" })}
            disabled={update.isPending}
          >
            I have this
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => update.mutate({ skillId: entry.skill.id, status: "rejected" })}
            disabled={update.isPending}
          >
            Not mine
          </Button>
        </div>
      ) : (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => update.mutate({ skillId: entry.skill.id, status: "rejected" })}
          disabled={update.isPending}
        >
          Remove
        </Button>
      )}
    </li>
  );
}

export default function SkillsPage() {
  const { data: profile, isLoading } = useSkillProfile();
  const { data: catalogue } = useSkillCatalogue();
  const addSkill = useAddSkill();
  const confirmAll = useConfirmAllSkills();
  // Also needed at page level: the "currently learning" list below marks skills learned,
  // which is the same status change SkillRow performs for suggestions.
  const update = useUpdateSkill();
  const [search, setSearch] = useState("");

  const owned = useMemo(() => {
    const ids = new Set<string>();
    profile?.confirmed.forEach((entry) => ids.add(entry.skill.id));
    profile?.suggested.forEach((entry) => ids.add(entry.skill.id));
    profile?.learning.forEach((entry) => ids.add(entry.skill.id));
    return ids;
  }, [profile]);

  const matches = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (term.length < 2 || !catalogue) return [];
    return catalogue
      .filter((skill) => !owned.has(skill.id) && skill.canonical_name.toLowerCase().includes(term))
      .slice(0, 6);
  }, [search, catalogue, owned]);

  if (isLoading) return <Spinner label="Loading your profile" />;

  const empty = profile && profile.total_confirmed === 0 && profile.total_suggested === 0;

  return (
    <>
      <PageHeader
        title="My skills"
        description="Extraction is a starting point, not a verdict. Correcting it here improves every match score and learning path."
        action={
          profile && profile.total_suggested > 0 ? (
            <Button onClick={() => confirmAll.mutate()} disabled={confirmAll.isPending}>
              Confirm all {profile.total_suggested}
            </Button>
          ) : undefined
        }
      />

      {empty ? (
        <EmptyState
          title="No skills yet"
          description="Upload a resume from the dashboard and we will extract your skills automatically. You can also add them by hand below."
        />
      ) : null}

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <div className="flex items-center justify-between px-5 py-4">
            <h2 className="text-sm font-semibold">Awaiting your review</h2>
            <Badge tone="warn">{profile?.total_suggested ?? 0}</Badge>
          </div>
          {profile && profile.suggested.length > 0 ? (
            <ul className="border-t border-[var(--color-line)]">
              {profile.suggested.map((entry) => (
                <SkillRow key={entry.skill.id} entry={entry} suggested />
              ))}
            </ul>
          ) : (
            <p className="border-t border-[var(--color-line)] px-5 py-6 text-sm text-[var(--color-muted)]">
              Nothing to review. Upload a resume and we will suggest the skills we find.
            </p>
          )}
        </Card>

        <div className="space-y-6">
          {/* Learning sits above Confirmed because it is the list the user is acting on.
              These skills deliberately do not count toward any score yet -- only marking one
              learned moves the number. */}
          {profile && profile.learning.length > 0 ? (
            <Card>
              <div className="flex items-center justify-between px-5 py-4">
                <h2 className="text-sm font-semibold">Currently learning</h2>
                <Badge tone="brand">{profile.total_learning}</Badge>
              </div>
              <ul className="border-t border-[var(--color-line)]">
                {profile.learning.map((entry) => (
                  <li
                    key={entry.skill.id}
                    className="flex items-center justify-between gap-3 px-5 py-3"
                  >
                    <span className="truncate text-sm">{entry.skill.canonical_name}</span>
                    <Button
                      size="sm"
                      onClick={() =>
                        update.mutate({ skillId: entry.skill.id, status: "confirmed" })
                      }
                    >
                      I&apos;ve learned this
                    </Button>
                  </li>
                ))}
              </ul>
              <p className="border-t border-[var(--color-line)] px-5 py-3 text-xs text-[var(--color-muted)]">
                Not counted toward your score until you mark them learned.
              </p>
            </Card>
          ) : null}

          <Card>
            <div className="flex items-center justify-between px-5 py-4">
              <h2 className="text-sm font-semibold">Confirmed</h2>
              <Badge tone="positive">{profile?.total_confirmed ?? 0}</Badge>
            </div>
            {profile && profile.confirmed.length > 0 ? (
              <ul className="border-t border-[var(--color-line)]">
                {profile.confirmed.map((entry) => (
                  <SkillRow key={entry.skill.id} entry={entry} suggested={false} />
                ))}
              </ul>
            ) : (
              <p className="border-t border-[var(--color-line)] px-5 py-6 text-sm text-[var(--color-muted)]">
                No confirmed skills yet.
              </p>
            )}
          </Card>

          <Card className="p-5">
            <h2 className="text-sm font-semibold">Add something we missed</h2>
            <div className="mt-3">
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search skills"
                aria-label="Search skills"
              />
            </div>
            {matches.length > 0 ? (
              <ul className="mt-3 space-y-1.5">
                {matches.map((skill) => (
                  <li key={skill.id} className="flex items-center justify-between gap-3">
                    <span className="text-sm">{skill.canonical_name}</span>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        addSkill.mutate(skill.id);
                        setSearch("");
                      }}
                    >
                      Add
                    </Button>
                  </li>
                ))}
              </ul>
            ) : null}
          </Card>
        </div>
      </div>
    </>
  );
}
