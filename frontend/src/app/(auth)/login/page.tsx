"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login(email, password);
    } catch (caught) {
      // The API returns the same message for a wrong password and an unknown account, on
      // purpose — surfacing it verbatim keeps that property intact rather than helpfully
      // telling an attacker which addresses exist.
      setError(caught instanceof Error ? caught.message : "Could not sign in.");
      setPending(false);
    }
  }

  return (
    <Card className="p-7">
      <h1 className="text-xl font-semibold tracking-tight">Sign in</h1>
      <p className="mt-1 text-sm text-[var(--color-muted)]">Welcome back.</p>

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
        <Field label="Password">
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </Field>
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
