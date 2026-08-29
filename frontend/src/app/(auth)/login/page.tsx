"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { GoogleSignInButton, OrDivider } from "@/components/GoogleSignInButton";
import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login, resendVerification } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [unverified, setUnverified] = useState(false);
  const [resent, setResent] = useState(false);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setUnverified(false);
    setPending(true);
    try {
      await login(email, password);
    } catch (caught) {
      // A 403 here means the password was right but the account is not verified yet — a
      // meaningfully different situation from a wrong password, so it gets its own
      // affordance instead of a generic error message.
      if (caught instanceof ApiError && caught.status === 403) {
        setUnverified(true);
      } else {
        // The API returns the same message for a wrong password and an unknown account, on
        // purpose — surfacing it verbatim keeps that property intact rather than helpfully
        // telling an attacker which addresses exist.
        setError(caught instanceof Error ? caught.message : "Could not sign in.");
      }
      setPending(false);
    }
  }

  async function onResend() {
    await resendVerification(email);
    setResent(true);
  }

  return (
    <Card className="p-7">
      <h1 className="text-xl font-semibold tracking-tight">Sign in</h1>
      <p className="mt-1 text-sm text-[var(--color-muted)]">Welcome back.</p>

      <div className="mt-6">
        <GoogleSignInButton />
      </div>
      <OrDivider />

      <form onSubmit={onSubmit} className="space-y-4">
        {error ? <Alert>{error}</Alert> : null}
        {unverified ? (
          <Alert tone="warn">
            <p>Confirm your email before signing in.</p>
            <button
              type="button"
              onClick={() => void onResend()}
              className="mt-1 font-medium underline"
            >
              {resent ? "Sent again ✓" : "Resend the verification email"}
            </button>
          </Alert>
        ) : null}
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
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-sm font-medium text-[var(--color-ink)]">Password</span>
            <Link
              href="/forgot-password"
              className="text-xs font-medium text-[var(--color-brand)]"
            >
              Forgot your password?
            </Link>
          </div>
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </div>
        <Button type="submit" disabled={pending} className="w-full">
          {pending ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <p className="mt-5 text-sm text-[var(--color-muted)]">
        No account?{" "}
        <Link href="/register" className="font-medium text-[var(--color-brand)]">
          Create one
        </Link>
      </p>
    </Card>
  );
}
