"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import type { UserRole } from "@/lib/types";

const MIN_PASSWORD_LENGTH = 12;

export default function RegisterPage() {
  const { register } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<UserRole>("job_seeker");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await register({ email, password, full_name: fullName || undefined, role });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create your account.");
      setPending(false);
    }
  }

  return (
    <Card className="p-7">
      <h1 className="text-xl font-semibold tracking-tight">Create your account</h1>
      <p className="mt-1 text-sm text-[var(--color-muted)]">Free, and takes a moment.</p>

      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        {error ? <Alert>{error}</Alert> : null}
        <Field label="Full name" hint="Optional.">
          <Input value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" />
        </Field>
        <Field label="Email">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
        </Field>
        <Field
          label="Password"
          hint={`At least ${MIN_PASSWORD_LENGTH} characters. Length beats complexity — a passphrase is stronger than P@ssw0rd!`}
          error={tooShort ? `Use at least ${MIN_PASSWORD_LENGTH} characters.` : undefined}
        >
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={MIN_PASSWORD_LENGTH}
            autoComplete="new-password"
          />
        </Field>
        <Field label="I am a" hint="Recruiters can publish public job postings.">
          <div className="flex gap-2">
            {(["job_seeker", "recruiter"] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setRole(option)}
                aria-pressed={role === option}
                className={`flex-1 rounded-lg border px-3 py-2.5 text-sm font-medium transition ${
                  role === option
                    ? "border-[var(--color-brand)] bg-[var(--color-brand-soft)] text-[var(--color-brand)]"
                    : "border-[var(--color-line)] bg-[var(--color-surface)] text-[var(--color-muted)]"
                }`}
              >
                {option === "job_seeker" ? "Job seeker" : "Recruiter"}
              </button>
            ))}
          </div>
        </Field>
        <Button type="submit" disabled={pending || tooShort} className="w-full">
          {pending ? "Creating…" : "Create account"}
        </Button>
      </form>

      <p className="mt-5 text-sm text-[var(--color-muted)]">
        Already have one?{" "}
        <Link href="/login" className="font-medium text-[var(--color-brand)]">
          Sign in
        </Link>
      </p>
    </Card>
  );
}
