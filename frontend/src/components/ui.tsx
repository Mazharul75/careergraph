"use client";

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

/**
 * A small set of primitives, deliberately.
 *
 * Every screen composes from these rather than reaching for arbitrary Tailwind classes, which
 * is what stops the interface drifting into "several apps in a trench coat". This is not a
 * design system — it is the smallest thing that keeps spacing, radius, and colour consistent.
 */

function cx(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(" ");
}

/* ------------------------------------------------------------------------------ layout */

export function Card({
  children,
  className,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article" | "li";
}) {
  return (
    <Tag
      className={cx(
        "rounded-xl border border-[var(--color-line)] bg-[var(--color-surface)] shadow-[0_1px_2px_rgba(11,17,32,0.04)]",
        className,
      )}
    >
      {children}
    </Tag>
  );
}

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-ink)]">{title}</h1>
        {description ? <p className="mt-1 max-w-2xl text-sm text-[var(--color-muted)]">{description}</p> : null}
      </div>
      {action}
    </header>
  );
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <Card className="p-10 text-center">
      <p className="text-sm font-medium text-[var(--color-ink)]">{title}</p>
      <p className="mx-auto mt-2 max-w-md text-sm text-[var(--color-muted)]">{description}</p>
      {action ? <div className="mt-5 flex justify-center">{action}</div> : null}
    </Card>
  );
}

/* ------------------------------------------------------------------------------ inputs */

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
};

const BUTTON_VARIANTS: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary: "bg-[var(--color-brand)] text-white hover:brightness-110",
  secondary:
    "border border-[var(--color-line)] bg-[var(--color-surface)] text-[var(--color-ink)] hover:bg-[var(--color-canvas)]",
  ghost: "text-[var(--color-muted)] hover:bg-[var(--color-canvas)] hover:text-[var(--color-ink)]",
  danger: "bg-[var(--color-danger)] text-white hover:brightness-110",
};

export function Button({ variant = "primary", size = "md", className, ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "px-3 py-1.5 text-sm" : "px-4 py-2.5 text-sm",
        BUTTON_VARIANTS[variant],
        className,
      )}
    />
  );
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-[var(--color-ink)]">{label}</span>
      {children}
      {error ? (
        <span className="mt-1.5 block text-sm text-[var(--color-danger)]">{error}</span>
      ) : hint ? (
        <span className="mt-1.5 block text-xs text-[var(--color-muted)]">{hint}</span>
      ) : null}
    </label>
  );
}

const CONTROL =
  "w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] px-3 py-2.5 text-sm text-[var(--color-ink)] placeholder:text-[var(--color-muted)]/70";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(CONTROL, props.className)} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx(CONTROL, "min-h-32 resize-y", props.className)} />;
}

/* ----------------------------------------------------------------------------- display */

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "brand" | "positive" | "warn" | "danger";
}) {
  const tones = {
    neutral: "bg-[var(--color-canvas)] text-[var(--color-muted)]",
    brand: "bg-[var(--color-brand-soft)] text-[var(--color-brand)]",
    positive: "bg-[var(--color-positive-soft)] text-[var(--color-positive)]",
    warn: "bg-[var(--color-warn-soft)] text-[var(--color-warn)]",
    danger: "bg-[var(--color-danger-soft)] text-[var(--color-danger)]",
  } as const;
  return (
    <span className={cx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", tones[tone])}>
      {children}
    </span>
  );
}

export function Alert({ tone = "danger", children }: { tone?: "danger" | "warn" | "brand"; children: ReactNode }) {
  const tones = {
    danger: "border-[var(--color-danger)]/30 bg-[var(--color-danger-soft)] text-[var(--color-danger)]",
    warn: "border-[var(--color-warn)]/30 bg-[var(--color-warn-soft)] text-[var(--color-warn)]",
    brand: "border-[var(--color-brand)]/30 bg-[var(--color-brand-soft)] text-[var(--color-brand)]",
  } as const;
  return (
    <div role="alert" className={cx("rounded-lg border px-3.5 py-2.5 text-sm", tones[tone])}>
      {children}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-[var(--color-muted)]">
      <span
        aria-hidden
        className="size-4 animate-spin rounded-full border-2 border-[var(--color-line)] border-t-[var(--color-brand)]"
      />
      {label}
    </span>
  );
}

/** A labelled progress bar. `value` is 0-100. */
export function Meter({ value, tone = "brand" }: { value: number; tone?: "brand" | "positive" }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      role="meter"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
      className="h-2 w-full overflow-hidden rounded-full bg-[var(--color-canvas)]"
    >
      <div
        className="h-full rounded-full transition-[width] duration-500"
        style={{
          width: `${clamped}%`,
          background: tone === "positive" ? "var(--color-positive)" : "var(--color-brand)",
        }}
      />
    </div>
  );
}
