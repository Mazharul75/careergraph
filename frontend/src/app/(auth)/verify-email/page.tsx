"use client";

/**
 * Where an emailed verification link lands.
 *
 * Reads the token from the URL and redeems it on mount — there is no form here, the click
 * itself is the action. Three states only: working, succeeded, failed (bad or already-used
 * link), each with exactly one next step so nobody is left staring at a dead end.
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Alert, Button, Card, Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";

type Status = "verifying" | "success" | "error";

export default function VerifyEmailPage() {
  // useSearchParams reads from the URL at request time, so Next.js requires a Suspense
  // boundary around anything that calls it — otherwise the whole route would have to give
  // up static generation just for one query parameter.
  return (
    <Suspense
      fallback={
        <Card className="p-7">
          <Spinner label="Loading" />
        </Card>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  );
}

function VerifyEmailContent() {
  const params = useSearchParams();
  const token = params.get("token");
  const { verifyEmail } = useAuth();
  // No token at all is knowable the instant this renders — deriving it during render (rather
  // than setting it from inside the effect) is what the lint rule below is actually asking
  // for: an effect should synchronize with something external, not assign state it could
  // have computed up front.
  const [asyncStatus, setAsyncStatus] = useState<"verifying" | "success" | "error" | null>(null);
  const status: Status = token ? (asyncStatus ?? "verifying") : "error";

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    verifyEmail(token)
      .then(() => {
        if (!cancelled) setAsyncStatus("success");
      })
      .catch(() => {
        if (!cancelled) setAsyncStatus("error");
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once for this token, not on every render
  }, [token]);

  return (
    <Card className="p-7 text-center">
      {status === "verifying" ? (
        <>
          <h1 className="text-xl font-semibold tracking-tight">Confirming your email</h1>
          <div className="mt-6 flex justify-center">
            <Spinner label="One moment" />
          </div>
        </>
      ) : status === "success" ? (
        <>
          <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-[var(--color-positive-soft)] text-2xl">
            ✓
          </div>
          <h1 className="mt-4 text-xl font-semibold tracking-tight">Email confirmed</h1>
          <p className="mt-1.5 text-sm text-[var(--color-muted)]">
            Your address is verified. You can sign in now.
          </p>
          <Link href="/login" className="mt-6 inline-block">
            <Button className="w-full">Continue to sign in</Button>
          </Link>
        </>
      ) : (
        <>
          <h1 className="text-xl font-semibold tracking-tight">Link invalid or expired</h1>
          <Alert>
            This verification link no longer works — it may already have been used, or it
            has expired.
          </Alert>
          <Link href="/login" className="mt-5 inline-block">
            <Button variant="secondary" className="w-full">
              Back to sign in
            </Button>
          </Link>
        </>
      )}
    </Card>
  );
}
