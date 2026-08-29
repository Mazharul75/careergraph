import { ImageResponse } from "next/og";

/**
 * The social share card, generated on request rather than stored as a static asset.
 *
 * `next/og` renders this as a real PNG through Vercel's built-in edge image generator — free,
 * no external design tool, and it can never drift out of sync with the brand palette because
 * it is built from the same tokens as the rest of the site.
 */
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          background: "linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%)",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div
            style={{
              display: "flex",
              width: 72,
              height: 72,
              borderRadius: 20,
              background: "#4f46e5",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <svg width="40" height="40" viewBox="0 0 32 32" fill="none">
              <path
                d="M9 21.5 L14.5 12.5 L20 17 L24 10.5"
                stroke="white"
                strokeWidth="2.6"
                strokeLinecap="round"
                strokeLinejoin="round"
                fill="none"
              />
              <circle cx="9" cy="21.5" r="2.6" fill="white" />
              <circle cx="14.5" cy="12.5" r="2.6" fill="white" />
              <circle cx="20" cy="17" r="2.6" fill="white" />
            </svg>
          </div>
          <span style={{ fontSize: 40, fontWeight: 700, color: "white" }}>CareerGraph</span>
        </div>

        <div
          style={{
            display: "flex",
            fontSize: 56,
            fontWeight: 800,
            color: "white",
            marginTop: 48,
            lineHeight: 1.15,
            maxWidth: 980,
          }}
        >
          Stop guessing what to learn next.
        </div>

        <div
          style={{
            display: "flex",
            fontSize: 28,
            color: "#c7d2fe",
            marginTop: 28,
            maxWidth: 880,
          }}
        >
          An ordered learning plan, built from a 113-skill prerequisite graph.
        </div>
      </div>
    ),
    { ...size },
  );
}
