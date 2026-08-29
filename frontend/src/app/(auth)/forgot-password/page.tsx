"use client";

/**
 * "Forgot your password" — email in, always the same reassuring message back out.
 *
 * The response is identical whether the address exists, already has no password (a
 * Google-only account), or was never registered at all — the frontend has no way to tell
 * these apart and should not try to. Showing anything more specific than "check your inbox"
 * would recreate the exact enumeration the backend was careful to avoid.
 */

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function ForgotPasswordPage() {
  const { forgotPassword } = useAuth();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [devToken, setDevToken] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const result = await forgotPassword(email);
      setDevToken(result.dev_reset_token);
      setSent(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong.");
    } finally {
      setPending(false);
    }
  }

  if (sent) {
    return (
      <Card className="p-7 text-center">
        <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-[var(--color-brand-soft)] text-2xl">
          ✉️
        </div>
        <h1 className="mt-4 text-xl font-semibold tracking-tight">Check your inbox</h1>
        <p className="mt-1.5 text-sm text-[var(--color-muted)]">
          If an account exists for <strong className="text-[var(--color-ink)]">{email}</strong>,
          a reset link is on its way. It expires in one hour.
        </p>
        {devToken ? (
          <Link
            href={`/reset-password?token=${devToken}`}
            className="mt-4 inline-block text-xs text-[var(--color-muted)] underline"
          >
            Dev mode: skip the inbox and reset now
          </Link>
        ) : null}
        <Link href="/login" className="mt-6 inline-block">
          <Button variant="secondary" className="w-full">
            Back to sign in
          </Button>
        </Link>
      </Card>
    );
  }

  return (
    <Card className="p-7">
      <h1 className="text-xl font-semibold tracking-tight">Reset your password</h1>
      <p className="mt-1 text-sm text-[var(--color-muted)]">
        Enter the email on your account and we&apos;ll send a link to choose a new one.
      </p>

      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        {error ? <Alert>{error}</Alert> : null}
        <Field label="Email">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            autoFocus
          />
        </Field>
        <Button type="submit" disabled={pending} className="w-full">
          {pending ? "Sending…" : "Send reset link"}
        </Button>
      </form>

      <p className="mt-5 text-sm text-[var(--color-muted)]">
        <Link href="/login" className="font-medium text-[var(--color-brand)]">
          Back to sign in
        </Link>
      </p>
    </Card>
  );
}
