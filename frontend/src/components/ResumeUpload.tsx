"use client";

import { useRef, useState } from "react";

import { Alert, Badge, Button, Card, Spinner } from "@/components/ui";
import { useResumes, useUploadResume } from "@/lib/queries";
import type { ParseStatus, Resume } from "@/lib/types";

const MAX_BYTES = 5 * 1024 * 1024;
const ACCEPTED = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];

const STATUS_LABEL: Record<ParseStatus, string> = {
  pending: "Queued",
  processing: "Reading your resume…",
  complete: "Parsed",
  failed: "Could not read",
};

function StatusBadge({ status }: { status: ParseStatus }) {
  if (status === "complete") return <Badge tone="positive">Parsed</Badge>;
  if (status === "failed") return <Badge tone="danger">Failed</Badge>;
  return <Badge tone="warn">{STATUS_LABEL[status]}</Badge>;
}

function ResumeRow({ resume }: { resume: Resume }) {
  const working = resume.status === "pending" || resume.status === "processing";
  return (
    <li className="flex flex-wrap items-center gap-3 border-t border-[var(--color-line)] px-5 py-3.5 first:border-t-0">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{resume.original_filename}</p>
        <p className="text-xs text-[var(--color-muted)]">
          {(resume.size_bytes / 1024).toFixed(0)} KB · {new Date(resume.created_at).toLocaleString()}
        </p>
        {resume.error_message ? (
          <p className="mt-1 text-xs text-[var(--color-danger)]">{resume.error_message}</p>
        ) : null}
      </div>
      {working ? <Spinner label={STATUS_LABEL[resume.status]} /> : <StatusBadge status={resume.status} />}
    </li>
  );
}

export function ResumeUpload() {
  const { data: resumes, isLoading } = useResumes();
  const upload = useUploadResume();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  function submit(file: File | undefined) {
    setError(null);
    if (!file) return;

    // Validated here as well as on the server. The client check exists purely to give instant
    // feedback — the server's check is the one that matters, since anything here can be
    // bypassed by talking to the API directly.
    if (!ACCEPTED.includes(file.type)) {
      setError("Please upload a PDF or DOCX file.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("That file is larger than 5 MB.");
      return;
    }
    upload.mutate(file, { onError: (e) => setError(e instanceof Error ? e.message : "Upload failed.") });
  }

  return (
    <Card>
      <div className="p-5">
        <h2 className="text-sm font-semibold">Your resume</h2>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          PDF or DOCX, up to 5 MB. Parsing happens in the background — you can keep working.
        </p>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            submit(e.dataTransfer.files[0]);
          }}
          className={`mt-4 rounded-xl border-2 border-dashed p-8 text-center transition ${
            dragging
              ? "border-[var(--color-brand)] bg-[var(--color-brand-soft)]"
              : "border-[var(--color-line)] bg-[var(--color-canvas)]"
          }`}
        >
          <p className="text-sm text-[var(--color-muted)]">Drag a file here, or</p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-3"
            onClick={() => inputRef.current?.click()}
            disabled={upload.isPending}
          >
            {upload.isPending ? "Uploading…" : "Choose a file"}
          </Button>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx"
            className="sr-only"
            onChange={(e) => {
              submit(e.target.files?.[0]);
              e.target.value = ""; // allow re-uploading the same filename
            }}
          />
        </div>

        {error ? (
          <div className="mt-4">
            <Alert>{error}</Alert>
          </div>
        ) : null}
      </div>

      {isLoading ? (
        <div className="border-t border-[var(--color-line)] px-5 py-4">
          <Spinner />
        </div>
      ) : resumes && resumes.length > 0 ? (
        <ul className="border-t border-[var(--color-line)]">
          {resumes.map((resume) => (
            <ResumeRow key={resume.id} resume={resume} />
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
