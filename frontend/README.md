# Frontend

Next.js 16 (App Router) + React 19 + TypeScript + Tailwind 4. Deployed to Vercel.

## Running it

```bash
cp .env.local.example .env.local
npm install
npm run dev
```

Needs the backend running (`docker compose up` from the repository root).

## Structure

| Path | What |
|---|---|
| `src/lib/api.ts` | Fetch client with transparent token refresh |
| `src/lib/auth.tsx` | Session state and the login/register/logout flows |
| `src/lib/queries.ts` | React Query hooks, including the polling rules |
| `src/components/ui.tsx` | The small primitive set every screen composes from |
| `src/app/(auth)/` | Login and register |
| `src/app/(app)/` | Authenticated shell: dashboard, skills, jobs |

## The one non-obvious piece

`api.ts` guards refresh with a **single-flight promise**, and that is not premature
optimisation — it is a correctness requirement created by
[ADR-0007](../docs/adr/0007-opaque-rotating-refresh-tokens.md).

Refresh tokens are single-use and rotating, and presenting a spent one is treated as theft: the
backend revokes the whole session family. So if three requests 401 simultaneously and each calls
`/auth/refresh` independently, the first succeeds and the other two present a token that was
just spent. The backend concludes the token was stolen and signs the user out — the security
control firing on our own client.

One in-flight refresh, awaited by every other request, is the fix.

## Token storage

The access token lives **in memory only**; the refresh token goes to `localStorage`. A page
reload therefore has no access token and derives one from the refresh token on mount — which is
why the app shell shows "Restoring your session" rather than bouncing to `/login`.
