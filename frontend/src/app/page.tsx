import Link from "next/link";

const STEPS = [
  {
    title: "Upload your resume",
    body: "We extract your skills automatically. Parsing runs in the background, so nothing blocks.",
  },
  {
    title: "Add a job description",
    body: "Paste any posting. We score the match on meaning, not shared keywords, and show the working.",
  },
  {
    title: "Get an ordered plan",
    body: "Not a pile of gaps — a sequence. Every skill appears after everything it depends on.",
  },
];

export default function LandingPage() {
  return (
    <main id="main" className="mx-auto max-w-4xl px-6 py-24">
      <p className="text-sm font-medium text-[var(--color-brand)]">CareerGraph</p>
      <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
        Know exactly which skills stand between you and the job — and what to learn first.
      </h1>
      <p className="mt-5 max-w-2xl text-lg text-[var(--color-muted)]">
        A posting asking for Kubernetes never mentions Docker or Linux. CareerGraph knows they
        come first, because skills are modelled as a dependency graph rather than a checklist.
      </p>

      <div className="mt-8 flex flex-wrap gap-3">
        <Link
          href="/register"
          className="rounded-lg bg-[var(--color-brand)] px-5 py-3 text-sm font-medium text-white transition hover:brightness-110"
        >
          Create an account
        </Link>
        <Link
          href="/login"
          className="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] px-5 py-3 text-sm font-medium transition hover:bg-white"
        >
          Sign in
        </Link>
      </div>

      <ol className="mt-16 grid gap-5 sm:grid-cols-3">
        {STEPS.map((step, index) => (
          <li
            key={step.title}
            className="rounded-xl border border-[var(--color-line)] bg-[var(--color-surface)] p-5"
          >
            <span className="inline-flex size-7 items-center justify-center rounded-full bg-[var(--color-brand-soft)] text-sm font-semibold text-[var(--color-brand)]">
              {index + 1}
            </span>
            <h2 className="mt-3 text-sm font-semibold">{step.title}</h2>
            <p className="mt-1.5 text-sm text-[var(--color-muted)]">{step.body}</p>
          </li>
        ))}
      </ol>
    </main>
  );
}
