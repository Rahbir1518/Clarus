# Clarus frontend

Next.js 16 (App Router), React 19, Tailwind CSS 4, Clerk. Setup, the full
start-up sequence (backend, ngrok, frontend) and troubleshooting are in the
[root README](../README.md).

```powershell
npm install
copy .env.example .env.local    # Clerk keys + NEXT_PUBLIC_API_URL; see the comments in the file
npm run dev                     # http://localhost:3000
```

The Clerk keys must belong to the same Clerk instance as the backend's
`CLERK_ISSUER`, or every API call 401s.

## Where things are

| Path | What |
|---|---|
| `app/(app)/` | Signed-in pages: dashboard, patients, workflow, triggers, calls, call-test, appointments, audit-log, settings |
| `app/(marketing)/`, `app/(auth)/` | Public pages, Clerk sign-in/up |
| `services/api.ts` | The only way to reach the backend — adds the Clerk token to every request |
| `hooks/useLiveEvents.ts` | Live updates from the backend's event stream |
| `components/calls/web-call.tsx` | Browser (WebRTC) calls to the ElevenLabs agent |
| `components/settings/` | Practice profile and clinic hours |
| `proxy.ts` | Route protection — every app route requires a session unless listed as public |

The browser never talks to Supabase; all data goes through the backend.

```powershell
npx tsc --noEmit
npx eslint .
```
