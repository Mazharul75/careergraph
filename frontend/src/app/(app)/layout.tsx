"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button, Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";

import type { UserRole } from "@/lib/types";

/**
 * Navigation is role-aware. `roles: undefined` means everyone sees it.
 *
 * Hiding a link is presentation, never protection -- the API enforces every one of these
 * independently. Showing an admin a link they cannot use would be the real bug.
 */
const NAV: { href: string; label: string; roles?: UserRole[] }[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/skills", label: "My skills" },
  { href: "/jobs", label: "Jobs" },
  { href: "/explore", label: "Explore" },
  { href: "/admin", label: "Admin", roles: ["admin"] },
  { href: "/settings", label: "Settings" },
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
      <header className="sticky top-0 z-40 border-b border-[var(--color-line)] bg-[var(--color-surface)]/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3.5">
          <Link href="/dashboard" className="flex items-center gap-2.5">
            <span className="flex size-7 items-center justify-center rounded-lg bg-[var(--color-brand)] font-display text-xs font-bold text-white">
              C
            </span>
            <span className="font-display text-sm font-bold tracking-tight">CareerGraph</span>
          </Link>

          <nav aria-label="Main" className="flex items-center gap-1">
            {NAV.filter((item) => !item.roles || item.roles.includes(user.role)).map((item) => {
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
