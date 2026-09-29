# Clarus — Codebase Audit

**Date:** 2026-07-25
**Scope:** Full review of `frontend/` and `backend/` at commit `dc1b946` (branch `main`)
**Context:** Project dormant for a period; a core team member has left. Goal is to establish what actually works, what external services need rotating or rebuilding, and what needs fixing before the project is picked back up.

> This document describes the code **as it actually is**, not as `README.md` describes it. Where the two disagree, that divergence is noted.

---

## Table of contents

1. [What this actually is](#1-what-this-actually-is)
2. [External services — what you need to redo](#2-external-services--what-you-need-to-redo)
3. [The database — you're rebuilding more than you think](#3-the-database--youre-rebuilding-more-than-you-think)
4. [Security — the serious findings](#4-security--the-serious-findings)
5. [Correctness bugs](#5-correctness-bugs)
6. [Dead and incomplete code](#6-dead-and-incomplete-code)
7. [Suggested order of work](#7-suggested-order-of-work)

---

## 1. What this actually is

A **medical workflow automation** app. Two deployables:

- **`frontend/`** — Next.js 16 / React 19, deployed to Vercel (`useclarus.vercel.app`)
- **`backend/`** — FastAPI, deployed to Render (`clarus-backend`, config in [render.yaml](render.yaml))

The real flow that works end-to-end:

```
Doctor builds a node graph in /workflow (React Flow)
  → saved as JSON nodes[]/edges[] in Supabase `workflows` table
  → POST /api/workflows/{id}/execute with a patient_id
  → workflow_engine.py BFS-walks the graph
  → "call_patient" node → ElevenLabs Conversational AI places a Twilio call
  → asyncio background task polls ElevenLabs every 30s (up to 20 min)
  → if patient confirmed → Google Calendar event via Auth0-stored Google token
```

Note the branding is inconsistent: the backend still calls itself **"MedTrigger"** everywhere ([backend/main.py:10](backend/main.py#L10), API title, calendar event descriptions patients would see). Only the frontend was rebranded to Clarus.

---

## 2. External services — what you need to redo

| Service | Where used | Status / action |
|---|---|---|
| **Supabase** | Backend only, via `SERVICE_ROLE_KEY` | Rebuild DB (see §3). Rotate service role key. |
| **Twilio** | SID/token/number in env; also `/api/twilio/voice` TwiML fallback | Rotate auth token. Number is linked *inside ElevenLabs*, not called directly for voice. |
| **ElevenLabs** | `ELEVENLABS_API_KEY`, `AGENT_ID`, `PHONE_NUMBER_ID` | Rotate key. **The agent itself lives in the ElevenLabs dashboard, not in this repo** — see §2a. |
| **Auth0** | Two apps: SPA (frontend login) + M2M (Management API) | Rotate both client secrets. Google social connection needs calendar scopes. |
| **Google Calendar** | No own credentials — piggybacks on Auth0's stored Google token | Configured through Auth0's Google connection. |
| **Web3Forms** | Contact form | **Access key hardcoded in source**: `f3934f91-...` at [frontend/app/(marketing)/contact/page.tsx:80](frontend/app/(marketing)/contact/page.tsx#L80). Submissions go to whichever email registered it — likely the departed member's. Rotate. |
| **Stripe** | Pricing page | **Test-mode payment links hardcoded** at [frontend/app/(marketing)/pricing/page.tsx:12-16](frontend/app/(marketing)/pricing/page.tsx#L12-L16). No Stripe integration exists beyond these links. |

### 2a. The critical unrecoverable dependency

The ElevenLabs agent's **prompt, its data-collection field schema, and its Twilio phone binding are all configured in the ElevenLabs dashboard** — none of it is in this repo. The backend just injects dynamic variables ([elevenlabs_service.py:64-74](backend/app/services/elevenlabs_service.py#L64-L74)) and then reads back six specific fields it expects the agent to have been configured to collect:

`call_outcome`, `patient_confirmed`, `confirmed_date`, `confirmed_time`, `doctor_name`, `patient_availability_notes`

If access to that ElevenLabs account is lost, **the agent must be rebuilt from scratch with those exact six data-collection fields recreated**, or the entire call→calendar pipeline silently produces nothing. The code's heavy transcript-scraping fallbacks ([endpoints.py:619-651](backend/app/api/endpoints.py#L619-L651)) exist precisely because these fields were unreliable — that is a signal this was already fragile.

### 2b. Git history — no leaked secrets

`backend/.env` **was** committed in the two initial commits (`baafae4`, `54ead0e`) and later removed. It was checked: **every value in it was empty** — it was a template, not a populated file. No credentials were ever exposed via git history.

Rotation is still warranted given a team member departed, but there is no public exposure to remediate.

---

## 3. The database — you're rebuilding more than you think

There is exactly **one** migration file, [backend/migrations/001_create_new_tables.sql](backend/migrations/001_create_new_tables.sql), and it only creates the *secondary* tables. It opens with foreign keys to `patients(id)`, `workflows(id)`, and `call_logs(id)` — **tables that no migration in this repo ever creates.**

The core schema was made by hand in the Supabase dashboard and never captured. It is gone. This is the single biggest thing to fix.

### Core tables to reconstruct

Reconstructed from code usage:

**`patients`** — `id` uuid pk, `doctor_id` text (Auth0 sub, *not* a uuid), `name`, `phone`, `dob` date, `mrn`, `insurance`, `primary_physician`, `last_visit`, `risk_level`, `notes`, `created_at`

> ⚠️ Four call sites do `patient.get("email")` to add a calendar attendee ([endpoints.py:717](backend/app/api/endpoints.py#L717), [:1039](backend/app/api/endpoints.py#L1039), [:1313](backend/app/api/endpoints.py#L1313), [workflow_engine.py:501](backend/app/services/workflow_engine.py#L501)) — but `email` is in **no** Pydantic model, no README schema, and no migration. Patients have never been invited to their own appointments. Add the column.

**`workflows`** — `id`, `doctor_id` text, `name`, `description`, `category`, `status` text (`DRAFT`/`ENABLED`), `nodes` jsonb, `edges` jsonb, `created_at`

> The code also reads `workflow.get("doctor_name")` ([workflow_engine.py:977](backend/app/services/workflow_engine.py#L977)) — another phantom column. Every AI call currently tells patients "your doctor" instead of a name.

**`call_logs`** — `id`, `workflow_id`, `patient_id`, `trigger_node`, `status`, `outcome`, `keypress`, `execution_log` jsonb, `created_at`

> [endpoints.py:1023](backend/app/api/endpoints.py#L1023) reads `call_log.get("doctor_id")` — also never created.

**`patient_conditions`** — `id`, `patient_id`, `icd10_code`, `description`, `hcc_category`, `raf_impact` numeric, `status`, `created_at`

**`patient_medications`** — `id`, `patient_id`, `name`, `dosage`, `frequency`, `route`, `prescriber`, `start_date`, `end_date`, `status`, `notes`, `created_at`

Plus the seven tables already covered by migration 001 (`notifications`, `lab_orders`, `referrals`, `staff_assignments`, `reports`, `pdf_documents`).

### Row Level Security

The backend uses the service role key exclusively, which **bypasses RLS entirely**. RLS policies today provide zero protection — all tenant isolation is a `WHERE doctor_id = ?` in application code, and as §4 shows, that is not enforced either.

---

## 4. Security — the serious findings

### 🔴 The API has no authentication. At all.

Not one of the ~40 endpoints in [backend/app/api/endpoints.py](backend/app/api/endpoints.py) checks a token. There is no dependency, no middleware, no JWT verification anywhere in the backend. `doctor_id` is an ordinary query parameter the client supplies.

Anyone who knows the Render URL can, with plain `curl`:

- `GET /api/patients` — **dump every patient record in the database**, no `doctor_id` needed (the filter is optional)
- `GET /api/call-logs` — read every call transcript (up to 5000 chars of patient conversation each)
- `POST /api/workflows/{id}/execute` — **place real phone calls to real patients**, burning Twilio/ElevenLabs balance
- `DELETE /api/patients/{id}` — delete anyone's records

This is PHI. It is fully public. Treat the deployed Render service as compromised-by-default and take it down or lock it before anything else.

### 🔴 The frontend "auth guard" doesn't guard

[frontend/app/(app)/layout.tsx:12](frontend/app/(app)/layout.tsx#L12) destructures `isAuthenticated` — and then never uses it. There is no redirect, no conditional. The dashboard, patient records, and call logs render for anyone who navigates there.

The README's "Routes & Protection" table claiming Auth0 protection on 9 routes is fiction. There is also no `middleware.ts` anywhere in the project.

### 🔴 Auth0 is login-only, and can't currently fix this

[Auth0ProviderWrapper.tsx](frontend/app/providers/Auth0ProviderWrapper.tsx) configures no `audience`, so Auth0 issues no API access token. [frontend/services/api.ts](frontend/services/api.ts) sends no `Authorization` header on any of its ~35 fetch calls.

Even if `Depends(verify_jwt)` were added to the backend tomorrow, the frontend has nothing to send. Both sides need work.

### 🟠 Cross-tenant leak in the workflow builder

[WorkflowBuilder.tsx:539](frontend/components/workflow/WorkflowBuilder.tsx#L539) calls `listWorkflows()` with **no doctorId**. The "Load Workflow" modal shows every doctor's workflows to every user. Other pages pass `doctorId` correctly — this one was missed.

### 🟠 Webhooks are unauthenticated and unverified

- `POST /api/elevenlabs/webhook` — no signature check. Anyone can POST a fake `conversation_id` + `patient_confirmed: true` and inject calendar events / falsify call outcomes.
- `POST /api/twilio/voice` and `/gather` — no Twilio signature validation (`X-Twilio-Signature`).

Both providers support request signing. Neither is used.

### 🟠 TwiML injection

[endpoints.py:1121](backend/app/api/endpoints.py#L1121) interpolates `call_log.outcome` straight into XML. A `<` or `&` breaks the response; crafted content injects TwiML verbs. Needs escaping.

### 🟡 CORS wildcard is silently non-functional

[backend/main.py:27](backend/main.py#L27) lists `"https://*.vercel.app"`. Starlette's `allow_origins` does **exact string matching** — it does not expand globs. That entry matches nothing.

Preview deployments have been failing CORS and nobody noticed, because the two literal URLs above it cover production. Use `allow_origin_regex` if wildcard behaviour is wanted.

---

## 5. Correctness bugs

### Google Calendar will break ~1 hour after each login

[google_calendar_service.py:104-108](backend/app/services/google_calendar_service.py#L104-L108) pulls `identity.access_token` from the Auth0 user profile. That is the token captured at login; Auth0 does not refresh it. Google access tokens expire in ~3600s.

Since the auto-poller runs up to 20 minutes *after* a call, and calls happen long after login, this fails in production far more often than in a demo. The refresh token plus a token-exchange step is needed.

### `trigger_node_type` is accepted and ignored

[`execute_workflow()`](backend/app/services/workflow_engine.py#L936) takes the parameter, documents it, and never reads it. `_find_trigger_node()` just returns the first trigger node it finds. A workflow with two triggers always fires the wrong one half the time.

### Failed actions don't stop the workflow

In the execution loop ([workflow_engine.py:1003-1017](backend/app/services/workflow_engine.py#L1003-L1017)), `condition_passed` is only set for condition nodes. If `call_patient` returns `ok=False`, successors run anyway — so "generate transcript" and "send summary" execute after a call that never happened.

### `generate_transcript` can never succeed inline

It fetches the ElevenLabs transcript ([workflow_engine.py:733](backend/app/services/workflow_engine.py#L733)) during synchronous execution — milliseconds after the call was initiated, while the phone is still ringing. It will always error. Only the background poller gets real transcripts.

### Background poller doesn't survive deploys

`asyncio.create_task(_auto_poll_call_result(...))` ([endpoints.py:812](backend/app/api/endpoints.py#L812)) holds state in process memory for up to 20 minutes. A Render restart, or a second worker, orphans in-flight calls — the call happens, the patient confirms, and no calendar event is ever created. Needs a durable queue or a cron-driven reconciler.

### Timezone mismatch

Dates resolve in `America/Toronto` ([endpoints.py:417](backend/app/api/endpoints.py#L417)) but calendar events are created as `America/New_York` ([google_calendar_service.py:129](backend/app/services/google_calendar_service.py#L129)). Same offset today, so it is invisible — until it isn't. Neither should be hardcoded.

### The "PM guess" heuristic

`_resolve_time()` ([endpoints.py:486](backend/app/api/endpoints.py#L486)) silently converts any hour < 8 to PM. A patient saying "7 AM" gets booked at 19:00. It is applied even to already-24-hour input.

### Transcript confirmation-detection is dangerously loose

`_detect_confirmation_from_transcript()` ([endpoints.py:296](backend/app/api/endpoints.py#L296)) matches a bare `\byes\b|\byeah\b|\bsure\b` anywhere in the transcript — including inside the agent's own lines, since the "only patient lines" claim in its docstring is not implemented.

"Yes, I understand, but no I can't make it" scores 1 confirm / 1 deny and reads as not-confirmed only by luck. This books appointments patients did not agree to.

### PDF lab-result regex matches almost anything

`_LAB_LINE_RE` ([pdf_service.py:26](backend/app/services/pdf_service.py#L26)) is `[A-Za-z\s\-/()]+? \d+\.?\d*` — any words followed by a number. It will extract addresses, dates, page numbers, and phone digits as "lab results."

Combined with `check_result_values` driving clinical branching, this is a patient-safety issue, not just a data-quality one.

### Minor

- **PDF is opened three times** ([pdf_service.py:234-241](backend/app/services/pdf_service.py#L234-L241)) — text, tables, then page count. Parse once.
- **`doctor_id` fallback strings** — `user?.sub ?? 'anonymous'` ([WorkflowBuilder.tsx:503](frontend/components/workflow/WorkflowBuilder.tsx#L503)) and `?? "unknown"` ([dashboard/page.tsx:109](frontend/app/(app)/dashboard/page.tsx#L109), [patients/page.tsx:59](frontend/app/(app)/patients/page.tsx#L59)). If Auth0 hasn't hydrated, records get permanently orphaned under a fake owner. Should block, not fall back.
- **`datetime.utcnow()`** ([pdf_service.py:250](backend/app/services/pdf_service.py#L250)) — deprecated in 3.12+. Local Python is 3.14 while Render pins 3.12.

---

## 6. Dead and incomplete code

- **`frontend/lib/supabase.ts` is never imported by anything.** The frontend has `@supabase/supabase-js` as a dependency and creates a client that no file uses — all data goes through the FastAPI backend. `NEXT_PUBLIC_SUPABASE_URL` / `_ANON_KEY` are documented in the README but functionally unused. Delete, or decide to use it.
- **`frontend/types/` is entirely dead** — all four files, zero imports. They also describe a *different* data model (`firstName`/`lastName` vs the actual `name`), so they are a stale design artifact that will actively mislead.
- **Five stub pages** that render a heading and nothing else: `settings/profile`, `settings/notifications`, `triggers/new`, `triggers/[triggerId]`, `triggers/[triggerId]/logs`.
- **`/triggers` is orphaned from navigation.** It is the *only* place to flip a workflow to `ENABLED` (which `/api/lab-event` requires to match anything), but [the sidebar](frontend/components/app/sidebar.tsx) doesn't link it — reachable only via the topbar command palette.
- **`checkCallStatus()`** is exported from `services/api.ts` and called by no component. Superseded by the server-side poller.
- **Backend read-only stubs**: `/api/notifications`, `/api/lab-orders`, `/api/referrals`, `/api/staff-assignments` are GET-only. The workflow engine writes these rows, but no UI reads them — created data is invisible.
- **No tests exist.** No test files, no test runner in either `package.json` or `requirements.txt`.
- **Root `.gitignore` is an Adobe Flash/ActionScript template** — `bin-debug/`, `*.swf`, `*.ipa`. Wrong file entirely, pasted from a generator. The real ignores live in the two subdirectory `.gitignore`s (which are correct).
- **`requirements.txt` is a full `pip freeze`** — 70+ pinned transitive deps including `pyiceberg` and `pyroaring`, which nothing imports. They arrive via `supabase`. Worth replacing with direct deps only.

---

## 7. Suggested order of work

### Immediate — the deployed backend is serving PHI publicly

1. Take the Render service offline, or put it behind an allowlist.
2. Rotate every credential: Supabase service role, Twilio auth token, ElevenLabs API key, both Auth0 client secrets, Web3Forms key.
3. Confirm owner access to the ElevenLabs account still exists. If not, that agent config is the thing to rebuild first — everything downstream depends on it (§2a).

### Then — the rebuild

4. Write `000_initial_schema.sql` capturing the five core tables (§3), including the missing `patients.email` and `workflows.doctor_name`. Get the whole schema into version control this time.
5. Add Auth0 JWT verification to the backend; derive `doctor_id` **from the verified token** rather than a query param, and enforce ownership on every row access.
6. Add the `audience` to `Auth0Provider` and an `Authorization` header to all of `services/api.ts`.
7. Actually implement the route guard in `(app)/layout.tsx`.
8. Verify webhook signatures for both ElevenLabs and Twilio; escape the TwiML.

### Then — correctness

9. Google token refresh (§5).
10. Move the poller to durable storage (§5).
11. Replace the transcript-scraping confirmation heuristic with properly-configured ElevenLabs data-collection fields, rather than patching the regexes (§5).

---

*No source files were modified in the course of this audit.*
