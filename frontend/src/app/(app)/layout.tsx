"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button, Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/skills", label: "My skills" },
  { href: "/jobs", label: "Jobs" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    // Wait for the session restore to settle before redirecting. Without the `loading` guard,
    // every page load would flash the login screen while the refresh request is in flight.
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner label="Restoring your session…" />
      </div>
    );
  }

  if (!user) return null; // redirecting

  return (
    <div className="min-h-dvh">
      <header className="border-b border-[var(--color-line)] bg-[var(--color-surface)]">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3.5">
          <Link href="/dashboard" className="text-sm font-semibold tracking-tight">
            CareerGraph
          </Link>

          <nav aria-label="Main" className="flex items-center gap-1">
            {NAV.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                    active
                      ? "bg-[var(--color-brand-soft)] text-[var(--color-brand)]"
                      : "text-[var(--color-muted)] hover:bg-[var(--color-canvas)]"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-sm text-[var(--color-muted)] sm:inline">{user.email}</span>
            <Button variant="ghost" size="sm" onClick={() => void logout()}>
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main id="main" className="mx-auto max-w-6xl px-6 py-10">
        {children}
      </main>
    </div>
  );
}
