"use client";

/**
 * Choose a new password from an emailed reset link.
 *
 * Worth saying out loud on this screen, not just in the backend: setting a new password ends
 * every other session on every device. That is the correct security behaviour, but a user
 * who is not told about it will be confused the next time their phone asks them to sign in
 * again — so the copy below says so plainly instead of leaving them to discover it.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { Alert, Button, Card, Field, Input, Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";

const MIN_PASSWORD_LENGTH = 12;

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <Card className="p-7">
          <Spinner label="Loading" />
        </Card>
      }
    >
      <ResetPasswordContent />
    </Suspense>
  );
}

function ResetPasswordContent() {
  const params = useSearchParams();
  const token = params.get("token");
  const router = useRouter();
  const { resetPassword } = useAuth();

  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    setError(null);
    setPending(true);
    try {
      await resetPassword(token, password);
      setDone(true);
      setTimeout(() => router.push("/login"), 2000);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "That link may be invalid or already used.",
      );
      setPending(false);
    }
  }

  if (!token) {
    return (
      <Card className="p-7 text-center">
        <h1 className="text-xl font-semibold tracking-tight">Missing reset link</h1>
        <Alert>Open this page from the link in your email, or request a new one.</Alert>
        <Link href="/forgot-password" className="mt-5 inline-block">
          <Button className="w-full">Request a new link</Button>
        </Link>
      </Card>
    );
  }

  if (done) {
    return (
      <Card className="p-7 text-center">
        <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-[var(--color-positive-soft)] text-2xl">
          ✓
        </div>
        <h1 className="mt-4 text-xl font-semibold tracking-tight">Password updated</h1>
        <p className="mt-1.5 text-sm text-[var(--color-muted)]">
          Taking you to sign in…
        </p>
      </Card>
    );
  }

  return (
    <Card className="p-7">
      <h1 className="text-xl font-semibold tracking-tight">Choose a new password</h1>
      <p className="mt-1 text-sm text-[var(--color-muted)]">
        This will sign you out everywhere else, on every device.
      </p>

      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        {error ? <Alert>{error}</Alert> : null}
        <Field
          label="New password"
          hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
          error={tooShort ? `Use at least ${MIN_PASSWORD_LENGTH} characters.` : undefined}
        >
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={MIN_PASSWORD_LENGTH}
            autoComplete="new-password"
            autoFocus
          />
        </Field>
        <Button type="submit" disabled={pending || tooShort} className="w-full">
          {pending ? "Updating…" : "Update password"}
        </Button>
      </form>
    </Card>
  );
}
