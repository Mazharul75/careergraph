import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // The API base URL is baked in at build time. NEXT_PUBLIC_ variables are inlined into the
  // client bundle, so this must never hold a secret — it is a public URL, which is fine.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
};

export default config;
