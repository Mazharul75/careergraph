/**
 * The CareerGraph mark: three nodes on a directed path, terminating in an arrowhead.
 *
 * Drawn rather than photographed or generated, on purpose — it is the same claim the whole
 * product makes, reduced to its simplest possible picture: skills are nodes, prerequisites are
 * directed edges, and the arrow only ever points toward "next." A wordmark alone cannot carry
 * that; a graph can, even at 24px.
 */
export function LogoMark({ className = "size-8" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="CareerGraph"
    >
      <rect width="32" height="32" rx="9" fill="var(--color-brand)" />
      <path
        d="M9 21.5 L14.5 12.5 L20 17 L24 10.5"
        stroke="white"
        strokeWidth="2.1"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <path
        d="M20.6 9.6 L24.4 10 L23.6 13.7"
        stroke="white"
        strokeWidth="2.1"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <circle cx="9" cy="21.5" r="2.1" fill="white" />
      <circle cx="14.5" cy="12.5" r="2.1" fill="white" />
      <circle cx="20" cy="17" r="2.1" fill="white" />
    </svg>
  );
}

/** Mark plus wordmark, for navigation bars. */
export function Logo({
  size = "md",
  withText = true,
}: {
  size?: "sm" | "md";
  withText?: boolean;
}) {
  const mark = size === "sm" ? "size-7" : "size-8";
  const text = size === "sm" ? "text-sm" : "text-base";
  return (
    <span className="flex items-center gap-2.5">
      <LogoMark className={mark} />
      {withText ? (
        <span className={`font-display ${text} font-bold tracking-tight`}>CareerGraph</span>
      ) : null}
    </span>
  );
}
