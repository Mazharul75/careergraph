import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";

import { Providers } from "./providers";
import "./globals.css";

/**
 * Fonts are self-hosted by `next/font`, not linked from Google's CDN.
 *
 * That matters for more than speed: a `<link>` to fonts.googleapis.com makes every visitor's
 * browser announce itself to a third party, and it adds a render-blocking round trip to
 * another origin. `next/font` downloads the files at build time, serves them from our own
 * domain, and emits `font-display: swap` with a size-adjusted fallback — so text is readable
 * immediately and does not jump when the real face arrives.
 */
const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-jakarta",
  display: "swap",
  weight: ["500", "600", "700", "800"],
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
  weight: ["500", "600"],
});

export const metadata: Metadata = {
  title: {
    default: "CareerGraph — turn a job posting into a study plan",
    template: "%s · CareerGraph",
  },
  description:
    "Upload your resume, paste the job you want, and get an ordered learning plan — every skill placed after the ones it depends on.",
  openGraph: {
    title: "CareerGraph — turn a job posting into a study plan",
    description:
      "Skill-gap analysis built on a prerequisite graph, so you learn things in an order that works.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${jakarta.variable} ${inter.variable} ${jetbrains.variable}`}
    >
      <body className="antialiased">
        {/* Keyboard and screen-reader users should not have to tab through the nav on every
            page to reach content. */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-[var(--color-brand)] focus:px-4 focus:py-2 focus:text-white"
        >
          Skip to content
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
