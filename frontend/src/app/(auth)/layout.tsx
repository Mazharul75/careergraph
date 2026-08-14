import Link from "next/link";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main id="main" className="mx-auto flex min-h-dvh max-w-md flex-col justify-center px-6 py-16">
      <Link href="/" className="mb-8 text-sm font-medium text-[var(--color-brand)]">
        CareerGraph
      </Link>
      {children}
    </main>
  );
}
