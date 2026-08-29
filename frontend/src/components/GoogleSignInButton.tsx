"use client";

/**
 * "Continue with Google", rendered by Google's own Identity Services widget.
 *
 * Rendering Google's actual button (rather than a lookalike we draw ourselves) matters for
 * more than looks: Google's terms require their mark to be reproduced exactly, and the real
 * widget is what actually knows how to open the One Tap / popup flow and hand back a signed
 * ID token — a hand-drawn copy would have nothing to wire up behind it.
 *
 * Entirely optional and self-hiding: with no `NEXT_PUBLIC_GOOGLE_CLIENT_ID` configured, this
 * renders nothing at all, mirroring the backend's own `GOOGLE_CLIENT_ID`-gated feature flag —
 * neither side ever shows a control the other can't act on.
 */

import Script from "next/script";
import { useEffect, useId, useRef, useState } from "react";

import { useAuth } from "@/lib/auth";

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

interface GoogleCredentialResponse {
  credential: string;
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: GoogleCredentialResponse) => void;
          }) => void;
          renderButton: (
            parent: HTMLElement,
            options: {
              type: "standard";
              theme: "outline";
              size: "large";
              width: number;
              text: "continue_with";
              shape: "pill";
            },
          ) => void;
        };
      };
    };
  }
}

export function GoogleSignInButton() {
  const { googleSignIn } = useAuth();
  const containerId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const [scriptReady, setScriptReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!scriptReady || !CLIENT_ID || !containerRef.current || !window.google) return;

    window.google.accounts.id.initialize({
      client_id: CLIENT_ID,
      callback: (response) => {
        void googleSignIn(response.credential).catch(() => {
          setError("Could not sign in with Google. Please try again.");
        });
      },
    });

    window.google.accounts.id.renderButton(containerRef.current, {
      type: "standard",
      theme: "outline",
      size: "large",
      width: 320,
      text: "continue_with",
      shape: "pill",
    });
  }, [scriptReady, googleSignIn]);

  if (!CLIENT_ID) return null;

  return (
    <div>
      <Script
        src="https://accounts.google.com/gsi/client"
        strategy="afterInteractive"
        onLoad={() => setScriptReady(true)}
      />
      <div className="flex justify-center" id={containerId} ref={containerRef} />
      {error ? (
        <p className="mt-2 text-center text-sm text-[var(--color-danger)]">{error}</p>
      ) : null}
    </div>
  );
}

/** A labelled divider between the Google button and the email/password form below it. */
export function OrDivider() {
  return (
    <div className="my-5 flex items-center gap-3">
      <div className="h-px flex-1 bg-[var(--color-line)]" />
      <span className="text-xs font-medium uppercase tracking-wide text-[var(--color-muted)]">
        or
      </span>
      <div className="h-px flex-1 bg-[var(--color-line)]" />
    </div>
  );
}
