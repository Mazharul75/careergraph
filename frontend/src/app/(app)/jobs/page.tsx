"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Spinner,
  Textarea,
} from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useCreateJob, useJobs } from "@/lib/queries";

const MIN_DESCRIPTION = 30;

export default function JobsPage() {
  const { user } = useAuth();
  const { data: jobs, isLoading } = useJobs();
  const createJob = useCreateJob();

  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [description, setDescription] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isRecruiter = user?.role === "recruiter";
  const tooShort = description.length > 0 && description.length < MIN_DESCRIPTION;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await createJob.mutateAsync({
        title,
        description,
        company: company || undefined,
        is_public: isPublic,
      });
      setTitle("");
      setCompany("");
      setDescription("");
      setIsPublic(false);
      setOpen(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save that job.");
    }
  }

  return (
    <>
      <PageHeader
        title="Jobs"
        description="Paste any posting. We extract what it requires and score you against it."
        action={
          <Button onClick={() => setOpen((value) => !value)}>{open ? "Cancel" : "Add a job"}</Button>
        }
      />

      {open ? (
        <Card className="mb-6 p-5">
          <form onSubmit={onSubmit} className="space-y-4">
            {error ? <Alert>{error}</Alert> : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Job title">
                <Input value={title} onChange={(e) => setTitle(e.target.value)} required autoFocus />
              </Field>
              <Field label="Company" hint="Optional.">
                <Input value={company} onChange={(e) => setCompany(e.target.value)} />
              </Field>
            </div>

            <Field
              label="Job description"
              hint="Paste the whole posting. More text means better skill extraction."
              error={tooShort ? `At least ${MIN_DESCRIPTION} characters.` : undefined}
            >
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                required
                minLength={MIN_DESCRIPTION}
              />
            </Field>

            {isRecruiter ? (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={isPublic}
                  onChange={(e) => setIsPublic(e.target.checked)}
                  className="size-4"
                />
                Publish publicly so candidates can find it
              </label>
            ) : null}

            <Button type="submit" disabled={createJob.isPending || tooShort}>
              {createJob.isPending ? "Saving…" : "Save job"}
            </Button>
          </form>
        </Card>
      ) : null}

      {isLoading ? (
        <Spinner label="Loading jobs" />
      ) : jobs && jobs.length > 0 ? (
        <ul className="grid gap-4 sm:grid-cols-2">
          {jobs.map((job) => (
            <Card key={job.id} as="li" className="transition hover:shadow-md">
              <Link href={`/jobs/${job.id}`} className="block p-5">
                <div className="flex items-start justify-between gap-3">
                  <h2 className="text-sm font-semibold">{job.title}</h2>
                  {job.is_public ? <Badge tone="brand">Public</Badge> : null}
                </div>
                {job.company ? (
                  <p className="mt-1 text-sm text-[var(--color-muted)]">{job.company}</p>
                ) : null}
                <p className="mt-3 text-xs text-[var(--color-muted)]">
                  {job.skill_count} skill{job.skill_count === 1 ? "" : "s"} identified
                </p>
              </Link>
            </Card>
          ))}
        </ul>
      ) : (
        <EmptyState
          title="No jobs yet"
          description="Paste a job description and we will show you your match score and exactly what to learn."
          action={<Button onClick={() => setOpen(true)}>Add your first job</Button>}
        />
      )}
    </>
  );
}
