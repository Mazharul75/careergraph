import Link from "next/link";

/**
 * The marketing surface.
 *
 * Structured around one asymmetry: everybody else's tool returns an unordered pile of missing
 * keywords, and this one returns a *sequence*. So the differentiator is not buried in a
 * feature list — it is shown, as an actual dependency chain, immediately under the headline.
 * A visitor who reads nothing else should still leave knowing what makes it different.
 */

/* ------------------------------------------------------------------------------ primitives */

function Container({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`mx-auto w-full max-w-6xl px-6 ${className}`}>{children}</div>;
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--color-brand)]">
      {children}
    </p>
  );
}

function SectionHeading({
  eyebrow,
  title,
  lede,
}: {
  eyebrow: string;
  title: string;
  lede?: string;
}) {
  return (
    <div className="max-w-2xl">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="mt-3 text-3xl font-bold sm:text-4xl">{title}</h2>
      {lede ? <p className="mt-4 text-lg leading-relaxed text-[var(--color-muted)]">{lede}</p> : null}
    </div>
  );
}

/* ------------------------------------------------------------------------ the visual proof */

const CHAIN = [
  { name: "Linux", note: "prerequisite", inferred: true },
  { name: "Networking", note: "prerequisite", inferred: true },
  { name: "Docker", note: "prerequisite", inferred: true },
  { name: "Kubernetes", note: "named in the posting", inferred: false },
];

/**
 * The product's whole argument in one card: a posting that says only "Kubernetes" produces a
 * four-step plan, and three of those steps were never mentioned in the job text.
 */
function OrderedPathCard() {
  return (
    <div className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-surface)] p-6 shadow-[var(--shadow-lg)]">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs font-medium text-[var(--color-muted)]">The posting says</p>
          <p className="mt-1 font-display text-sm font-semibold">
            &ldquo;Run our production Kubernetes clusters&rdquo;
          </p>
        </div>
        <span className="rounded-full bg-[var(--color-accent-soft)] px-2.5 py-1 text-xs font-semibold text-[var(--color-accent)]">
          4 steps
        </span>
      </div>

      <ol className="mt-5 space-y-2.5">
        {CHAIN.map((step, index) => (
          <li key={step.name} className="flex items-center gap-3">
            <span
              className={`tabular-figures flex size-7 shrink-0 items-center justify-center rounded-lg text-xs font-semibold ${
                step.inferred
                  ? "bg-[var(--color-brand-soft)] text-[var(--color-brand)]"
                  : "bg-[var(--color-brand)] text-white"
              }`}
            >
              {index + 1}
            </span>
            <div className="min-w-0 flex-1 rounded-lg border border-[var(--color-line)] px-3 py-2">
              <p className="text-sm font-medium">{step.name}</p>
            </div>
            <span
              className={`hidden shrink-0 text-xs sm:block ${
                step.inferred ? "text-[var(--color-muted)]" : "text-[var(--color-brand)]"
              }`}
            >
              {step.note}
            </span>
          </li>
        ))}
      </ol>

      <p className="mt-5 border-t border-[var(--color-line)] pt-4 text-xs leading-relaxed text-[var(--color-muted)]">
        Three of these four were never mentioned in the job description. A keyword scanner
        cannot produce them — they come from a prerequisite graph.
      </p>
    </div>
  );
}

/* ----------------------------------------------------------------------------------- data */

const PROBLEMS = [
  {
    title: "The gap is invisible",
    body: "A posting lists twenty requirements. Which do you already meet under a different name? “Built REST services in Python” and “FastAPI experience” are the same thing — keyword matching says they are unrelated.",
  },
  {
    title: "The gap is unordered",
    body: "Knowing you are missing Kubernetes, Docker and Linux does not tell you these have a natural order. Starting with Kubernetes wastes weeks and teaches you very little.",
  },
  {
    title: "It does not scale",
    body: "Comparing yourself to thirty postings by hand takes an evening and produces judgements that contradict each other by the end of it.",
  },
];

const STEPS = [
  {
    n: "01",
    title: "Upload your resume",
    body: "PDF or DOCX. Skills are extracted automatically in a background worker, so the upload returns instantly instead of making you wait on a parser.",
  },
  {
    n: "02",
    title: "Add the job you want",
    body: "Paste any posting. We score the match on meaning as well as keywords, and always show the working — which skills matched, which are missing.",
  },
  {
    n: "03",
    title: "Follow the plan",
    body: "Set it as your target and we freeze today's score. Mark skills learned as you go and watch the number climb toward the role.",
  },
];

const FEATURES = [
  {
    title: "Explainable scores",
    body: "Every score ships with the skills that matched and the skills that did not. An unexplained 73% is not actionable, and nobody trusts it.",
  },
  {
    title: "Semantic matching",
    body: "Your resume and each posting become vectors, so wording you never shared still counts. Different words, same competency.",
  },
  {
    title: "You can correct it",
    body: "Extraction is never perfect. Every extracted skill is a suggestion you confirm or reject, and a rejection never comes back.",
  },
  {
    title: "Progress you can see",
    body: "A frozen baseline plus a live score. Marking a skill learned is the only thing that moves the number — intentions are free.",
  },
  {
    title: "Nothing blocks",
    body: "Parsing and embedding run on a queue. Upload a ten-page resume and the interface stays responsive throughout.",
  },
  {
    title: "Your documents stay yours",
    body: "The uploaded file is discarded once its text is extracted. Recruiters see scores and skills — never your resume.",
  },
];

const FAQ = [
  {
    q: "How is this different from a resume keyword scanner?",
    a: "Scanners tell you which words are missing. CareerGraph knows that skills depend on each other, so it returns an ordered plan instead of a pile — and it infers prerequisites the posting never mentioned.",
  },
  {
    q: "Do I need to tag my own skills?",
    a: "No. Upload a resume and skills are extracted for you. You confirm or reject each one, because a wrong profile would poison every score that follows.",
  },
  {
    q: "What happens to my resume?",
    a: "The text is extracted, then the original file is deleted. We keep what is needed to score you and nothing more.",
  },
  {
    q: "Is it free?",
    a: "Yes. It runs on free-tier infrastructure, which means the first request after a quiet period can take a few seconds to wake up.",
  },
];

const STACK = [
  "FastAPI",
  "PostgreSQL + pgvector",
  "Celery + Redis",
  "NetworkX",
  "Next.js",
  "Docker",
];

/* ------------------------------------------------------------------------------------ page */

export default function LandingPage() {
  return (
    <div className="min-h-dvh">
      {/* --- Nav ------------------------------------------------------------------------ */}
      <header className="sticky top-0 z-40 border-b border-[var(--color-line)]/70 bg-[var(--color-surface)]/80 backdrop-blur-md">
        <Container className="flex h-16 items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-[var(--color-brand)] font-display text-sm font-bold text-white">
              C
            </span>
            <span className="font-display text-base font-bold tracking-tight">CareerGraph</span>
          </Link>

          <nav aria-label="Sections" className="hidden items-center gap-7 md:flex">
            {[
              ["How it works", "#how"],
              ["Features", "#features"],
              ["For recruiters", "#recruiters"],
              ["FAQ", "#faq"],
            ].map(([label, href]) => (
              <a
                key={href}
                href={href}
                className="text-sm font-medium text-[var(--color-muted)] transition hover:text-[var(--color-ink)]"
              >
                {label}
              </a>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <Link
              href="/login"
              className="rounded-lg px-3.5 py-2 text-sm font-medium text-[var(--color-muted)] transition hover:bg-[var(--color-canvas)] hover:text-[var(--color-ink)]"
            >
              Sign in
            </Link>
            <Link
              href="/register"
              className="rounded-lg bg-[var(--color-ink)] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[var(--color-ink-soft)]"
            >
              Get started
            </Link>
          </div>
        </Container>
      </header>

      <main id="main">
        {/* --- Hero -------------------------------------------------------------------- */}
        <section className="hero-wash relative overflow-hidden">
          <div aria-hidden className="grid-lines absolute inset-0" />
          <Container className="relative py-20 sm:py-28">
            <div className="grid items-center gap-14 lg:grid-cols-[1.05fr_0.95fr]">
              <div className="animate-rise">
                <span className="inline-flex items-center gap-2 rounded-full border border-[var(--color-line)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-medium text-[var(--color-muted)] shadow-[var(--shadow-xs)]">
                  <span className="size-1.5 rounded-full bg-[var(--color-positive)]" />
                  Built on a 113-skill prerequisite graph
                </span>

                <h1 className="mt-6 text-4xl font-extrabold leading-[1.08] sm:text-5xl lg:text-6xl">
                  Stop guessing
                  <br />
                  what to <span className="text-gradient">learn next</span>.
                </h1>

                <p className="mt-6 max-w-xl text-lg leading-relaxed text-[var(--color-muted)]">
                  CareerGraph reads your resume, compares it to the job you actually want, and
                  hands you an <strong className="font-semibold text-[var(--color-ink)]">ordered</strong>{" "}
                  learning plan — every skill placed after the ones it depends on.
                </p>

                <div className="mt-9 flex flex-wrap items-center gap-3">
                  <Link
                    href="/register"
                    className="rounded-xl bg-[var(--color-brand)] px-6 py-3.5 text-sm font-semibold text-white shadow-[var(--shadow-glow)] transition hover:bg-[var(--color-brand-deep)]"
                  >
                    Analyse my resume — free
                  </Link>
                  <a
                    href="#how"
                    className="rounded-xl border border-[var(--color-line-strong)] bg-[var(--color-surface)] px-6 py-3.5 text-sm font-semibold transition hover:bg-[var(--color-canvas)]"
                  >
                    See how it works
                  </a>
                </div>

                <p className="mt-5 text-sm text-[var(--color-muted)]">
                  No credit card. Your resume is deleted after its text is read.
                </p>
              </div>

              <div className="animate-rise [animation-delay:120ms]">
                <OrderedPathCard />
              </div>
            </div>
          </Container>
        </section>

        {/* --- Problem ----------------------------------------------------------------- */}
        <section className="border-y border-[var(--color-line)] bg-[var(--color-surface)] py-20 sm:py-24">
          <Container>
            <SectionHeading
              eyebrow="The problem"
              title="A job posting is not a study plan"
              lede="Every early-career developer has read a list of twenty requirements and had no idea where to begin. Three things go wrong, and they compound."
            />

            <div className="mt-12 grid gap-6 md:grid-cols-3">
              {PROBLEMS.map((problem, index) => (
                <div
                  key={problem.title}
                  className="rounded-xl border border-[var(--color-line)] bg-[var(--color-canvas)] p-6"
                >
                  <span className="tabular-figures text-sm font-semibold text-[var(--color-faint)]">
                    0{index + 1}
                  </span>
                  <h3 className="mt-3 text-lg font-semibold">{problem.title}</h3>
                  <p className="mt-2.5 text-sm leading-relaxed text-[var(--color-muted)]">
                    {problem.body}
                  </p>
                </div>
              ))}
            </div>
          </Container>
        </section>

        {/* --- How it works ------------------------------------------------------------ */}
        <section id="how" className="scroll-mt-20 py-20 sm:py-24">
          <Container>
            <SectionHeading
              eyebrow="How it works"
              title="Three steps, then a plan you can follow"
              lede="No manual tagging, no configuration, and nothing that makes you wait on a spinner."
            />

            <div className="mt-12 grid gap-6 md:grid-cols-3">
              {STEPS.map((step) => (
                <div
                  key={step.n}
                  className="relative rounded-xl border border-[var(--color-line)] bg-[var(--color-surface)] p-6 shadow-[var(--shadow-sm)]"
                >
                  <span className="tabular-figures text-2xl font-bold text-[var(--color-brand)]">
                    {step.n}
                  </span>
                  <h3 className="mt-3 text-lg font-semibold">{step.title}</h3>
                  <p className="mt-2.5 text-sm leading-relaxed text-[var(--color-muted)]">
                    {step.body}
                  </p>
                </div>
              ))}
            </div>
          </Container>
        </section>

        {/* --- Features ---------------------------------------------------------------- */}
        <section
          id="features"
          className="scroll-mt-20 border-y border-[var(--color-line)] bg-[var(--color-surface)] py-20 sm:py-24"
        >
          <Container>
            <SectionHeading
              eyebrow="What you get"
              title="Built to be trusted, not just to look clever"
              lede="Every number the product shows you can be traced back to the evidence behind it."
            />

            <div className="mt-12 grid gap-x-10 gap-y-9 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map((feature) => (
                <div key={feature.title}>
                  <div className="flex size-9 items-center justify-center rounded-lg bg-[var(--color-brand-soft)]">
                    <span className="size-2 rounded-full bg-[var(--color-brand)]" />
                  </div>
                  <h3 className="mt-4 font-semibold">{feature.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-[var(--color-muted)]">
                    {feature.body}
                  </p>
                </div>
              ))}
            </div>
          </Container>
        </section>

        {/* --- Recruiters -------------------------------------------------------------- */}
        <section id="recruiters" className="scroll-mt-20 py-20 sm:py-24">
          <Container>
            <div className="grid items-center gap-12 lg:grid-cols-2">
              <div>
                <SectionHeading
                  eyebrow="For recruiters"
                  title="The same engine, pointed the other way"
                  lede="Post a role and see every candidate ranked against it, with the reasoning attached. Because it is the same scoring code job seekers use, the two sides can never disagree about what a number means."
                />
                <ul className="mt-8 space-y-3.5">
                  {[
                    "Ranked by skill coverage and semantic similarity together",
                    "Every row shows which skills matched and which are missing",
                    "Candidates with no overlap are omitted, not padded in at 0%",
                    "Names and scores only — never resumes or contact details",
                  ].map((item) => (
                    <li key={item} className="flex gap-3 text-sm leading-relaxed">
                      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-[var(--color-brand)]" />
                      <span className="text-[var(--color-muted)]">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-surface)] p-6 shadow-[var(--shadow-md)]">
                <p className="text-xs font-medium text-[var(--color-muted)]">
                  Candidates for &ldquo;Backend Engineer&rdquo;
                </p>
                <div className="mt-4 space-y-3">
                  {[
                    { name: "A. Rahman", score: 86, has: ["Python", "Docker", "SQL"] },
                    { name: "S. Karim", score: 64, has: ["Python", "Git"] },
                    { name: "M. Hasan", score: 41, has: ["SQL"] },
                  ].map((c, i) => (
                    <div
                      key={c.name}
                      className="rounded-xl border border-[var(--color-line)] p-3.5"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="flex items-center gap-2.5">
                          <span className="tabular-figures flex size-6 items-center justify-center rounded-md bg-[var(--color-canvas)] text-xs font-semibold text-[var(--color-muted)]">
                            {i + 1}
                          </span>
                          <span className="text-sm font-medium">{c.name}</span>
                        </span>
                        <span className="tabular-figures text-sm font-bold">{c.score}%</span>
                      </div>
                      <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-[var(--color-canvas)]">
                        <div
                          className="h-full rounded-full bg-[var(--color-brand)]"
                          style={{ width: `${c.score}%` }}
                        />
                      </div>
                      <div className="mt-2.5 flex flex-wrap gap-1.5">
                        {c.has.map((s) => (
                          <span
                            key={s}
                            className="rounded-full bg-[var(--color-positive-soft)] px-2 py-0.5 text-xs font-medium text-[var(--color-positive)]"
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
                <p className="mt-4 text-xs text-[var(--color-muted)]">
                  Illustrative. Real rankings are computed from confirmed skill profiles.
                </p>
              </div>
            </div>
          </Container>
        </section>

        {/* --- Under the hood ---------------------------------------------------------- */}
        <section className="border-y border-[var(--color-line)] bg-[var(--color-ink)] py-20 text-white sm:py-24">
          <Container>
            <div className="max-w-2xl">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--color-brand-bright)]">
                Under the hood
              </p>
              <h2 className="mt-3 text-3xl font-bold sm:text-4xl">
                A real system, not a demo
              </h2>
              <p className="mt-4 text-lg leading-relaxed text-white/70">
                Background workers, vector search, and a directed acyclic graph of skills —
                deployed behind a pipeline that refuses to ship anything the tests do not pass.
              </p>
            </div>

            <div className="mt-12 grid gap-6 sm:grid-cols-3">
              {[
                {
                  k: "Ordered, not listed",
                  v: "Missing skills are topologically sorted over a prerequisite DAG, so nothing is ever suggested before what it depends on.",
                },
                {
                  k: "Meaning, not keywords",
                  v: "Sentence embeddings stored in Postgres with pgvector, compared by cosine similarity alongside skill coverage.",
                },
                {
                  k: "Nothing blocks a request",
                  v: "Parsing and embedding run on a Celery queue with idempotent tasks, so a worker restart never loses your upload.",
                },
              ].map((item) => (
                <div key={item.k} className="rounded-xl border border-white/10 bg-white/5 p-6">
                  <h3 className="font-semibold text-white">{item.k}</h3>
                  <p className="mt-2.5 text-sm leading-relaxed text-white/65">{item.v}</p>
                </div>
              ))}
            </div>

            <div className="mt-10 flex flex-wrap items-center gap-2.5">
              {STACK.map((tech) => (
                <span
                  key={tech}
                  className="rounded-full border border-white/15 px-3.5 py-1.5 text-xs font-medium text-white/75"
                >
                  {tech}
                </span>
              ))}
            </div>
          </Container>
        </section>

        {/* --- FAQ --------------------------------------------------------------------- */}
        <section id="faq" className="scroll-mt-20 py-20 sm:py-24">
          <Container>
            <SectionHeading eyebrow="Questions" title="Before you sign up" />

            <div className="mt-10 grid gap-4 sm:grid-cols-2">
              {FAQ.map((item) => (
                <details
                  key={item.q}
                  className="group rounded-xl border border-[var(--color-line)] bg-[var(--color-surface)] p-5 transition hover:border-[var(--color-line-strong)]"
                >
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-medium">
                    {item.q}
                    <span className="shrink-0 text-[var(--color-muted)] transition group-open:rotate-45">
                      +
                    </span>
                  </summary>
                  <p className="mt-3 text-sm leading-relaxed text-[var(--color-muted)]">
                    {item.a}
                  </p>
                </details>
              ))}
            </div>
          </Container>
        </section>

        {/* --- Final CTA --------------------------------------------------------------- */}
        <section className="pb-24">
          <Container>
            <div className="relative overflow-hidden rounded-2xl border border-[var(--color-line)] bg-[var(--color-surface)] px-8 py-14 text-center shadow-[var(--shadow-lg)]">
              <div
                aria-hidden
                className="absolute inset-0 bg-[radial-gradient(40rem_20rem_at_50%_-20%,rgb(99_102_241/0.14),transparent_70%)]"
              />
              <div className="relative">
                <h2 className="text-3xl font-bold sm:text-4xl">
                  Find out where you actually stand
                </h2>
                <p className="mx-auto mt-4 max-w-xl text-lg text-[var(--color-muted)]">
                  One resume, one job description, and about ninety seconds.
                </p>
                <Link
                  href="/register"
                  className="mt-8 inline-block rounded-xl bg-[var(--color-brand)] px-7 py-3.5 text-sm font-semibold text-white shadow-[var(--shadow-glow)] transition hover:bg-[var(--color-brand-deep)]"
                >
                  Create your free account
                </Link>
              </div>
            </div>
          </Container>
        </section>
      </main>

      {/* --- Footer -------------------------------------------------------------------- */}
      <footer className="border-t border-[var(--color-line)] bg-[var(--color-surface)] py-10">
        <Container className="flex flex-col items-center justify-between gap-4 sm:flex-row">
          <div className="flex items-center gap-2.5">
            <span className="flex size-7 items-center justify-center rounded-lg bg-[var(--color-brand)] font-display text-xs font-bold text-white">
              C
            </span>
            <span className="text-sm font-semibold">CareerGraph</span>
          </div>
          <p className="text-sm text-[var(--color-muted)]">
            Skill-gap analysis over a prerequisite graph.
          </p>
          <div className="flex gap-5 text-sm text-[var(--color-muted)]">
            <Link href="/login" className="transition hover:text-[var(--color-ink)]">
              Sign in
            </Link>
            <Link href="/register" className="transition hover:text-[var(--color-ink)]">
              Get started
            </Link>
          </div>
        </Container>
      </footer>
    </div>
  );
}
