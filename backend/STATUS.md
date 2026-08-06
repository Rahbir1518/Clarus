# Clarus backend — status, setup, and what's next

Current as of 2026-08-06. Companion to [README.md](README.md), which explains
*how* the foundation works; this file records *what is built*, *what you must
run*, and *what is deliberately missing*.

---

## Endpoint inventory

Everything the API serves today. Generated from the OpenAPI spec, not from
memory — regenerate with:

```bash
python -c "from app.main import app; import json; print(json.dumps(sorted(app.openapi()['paths']), indent=2))"
```

| Methods | Path |
|---|---|
| `GET` | `/health`, `/health/ready` |
| `GET` `POST` | `/api/patients` |
| `GET` `PUT` `DELETE` | `/api/patients/{patient_id}` |
| `GET` `POST` | `/api/patients/{patient_id}/conditions` |
| `PUT` `DELETE` | `/api/patients/{patient_id}/conditions/{condition_id}` |
| `GET` `POST` | `/api/patients/{patient_id}/medications` |
| `PUT` `DELETE` | `/api/patients/{patient_id}/medications/{medication_id}` |
| `GET` `POST` | `/api/workflows` |
| `GET` `PUT` `DELETE` | `/api/workflows/{workflow_id}` |
| `GET` | `/api/call-logs`, `/api/call-logs/{call_log_id}` |
| `GET` | `/api/events` — SSE stream |
| `POST` | `/api/elevenlabs/webhook` — signature-authenticated |

153 tests, all passing.

### Which frontend pages work

| Page | State |
|---|---|
| Patients, patient detail | ✅ |
| Triggers, workflow builder | ✅ |
| Calls (live-updating), appointments, audit log | ✅ |
| Dashboard | ⚠️ everything except the PDF intake button |

---

## Migrations — apply in this order

```bash
psql "$DATABASE_URL" -f migrations/000_initial_schema.sql
psql "$DATABASE_URL" -f migrations/001_rls.sql
psql "$DATABASE_URL" -f migrations/002_call_outcomes.sql
```

`reset.sql` exists for a development database whose tables were built by hand
in the dashboard. It is destructive and is not a migration — never run it in a
sequence, and never against real data.

`001_rls.sql` ends with a self-check that **aborts the migration** if any table
in `public` has RLS disabled. That is aimed at a future migration adding a table
nobody remembers to protect: it fails loudly at apply time rather than shipping
an unprotected table.

### Verifying the database

One query, failures sorted to the top. Every row should read `true`.

```sql
SELECT * FROM (
  SELECT 'anon has NO schema usage' AS check_name,
         NOT has_schema_privilege('anon','public','USAGE') AS pass
  UNION ALL SELECT 'authenticated has schema usage',
         has_schema_privilege('authenticated','public','USAGE')
  UNION ALL SELECT 'service_role has schema usage',
         has_schema_privilege('service_role','public','USAGE')
  UNION ALL SELECT 'no table grants for anon/authenticated',
         NOT EXISTS (SELECT 1 FROM information_schema.role_table_grants
                      WHERE table_schema='public' AND grantee IN ('anon','authenticated'))
  UNION ALL SELECT 'RLS enabled on every public table',
         NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                      WHERE n.nspname='public' AND c.relkind IN ('r','p')
                        AND NOT c.relrowsecurity)
  UNION ALL SELECT 'predicates executable by authenticated only',
         (SELECT bool_and(has_function_privilege('authenticated',p.oid,'EXECUTE')
                      AND NOT has_function_privilege('anon',p.oid,'EXECUTE'))
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname='public'
             AND p.proname IN ('current_doctor_id','owns_patient',
                               'owns_workflow','owns_call_log'))
) t ORDER BY pass, check_name;
```

To prove the policies actually refuse a cross-tenant write, run the block in
[migrations/001_rls.sql](migrations/001_rls.sql)'s header notes — seed two
tenants, grant `authenticated` just enough to reach the policies, attempt a
forged referral, and `ROLLBACK`. The `INSERT` erroring with `42501` is the pass
condition.

---

## Accounts and credentials

### Twilio — required, but never configured here

`app/integrations/elevenlabs/client.py` places calls through
`POST /v1/convai/twilio/outbound-call`. You buy a voice-capable number in
Twilio and import it into **ElevenLabs**, giving your Account SID and Auth
Token to ElevenLabs.

This backend never talks to Twilio directly. That is why `app/core/config.py`
has no Twilio settings and does not need any. Do not add them.

### ElevenLabs — four values

```bash
ELEVENLABS_API_KEY=...            # dashboard → profile → API key
ELEVENLABS_AGENT_ID=...           # printed by scripts/sync_agent.py on create
ELEVENLABS_PHONE_NUMBER_ID=...    # client.list_phone_numbers() after the Twilio import
ELEVENLABS_WEBHOOK_SECRET=...     # dashboard → webhooks, when registering the URL
```

The agent definition lives in `agents/*.yaml` and is the source of truth.
`scripts/sync_agent.py` pushes it. Editing the agent in the ElevenLabs
dashboard works until the next sync overwrites it — that is deliberate, because
the previous project lost its agent configuration when the dashboard was the
only copy.

`scripts/test_call.py` places one real call with no database, auth, or workflow
engine involved. It is the shortest path from "I have an account" to "my phone
rang and the agent behaved correctly". **It costs real money — point it at your
own number.**

### A publicly reachable URL

ElevenLabs must reach `/api/elevenlabs/webhook`. In development that means a
tunnel:

```bash
ngrok http 8000        # or: cloudflared tunnel --url http://localhost:8000
```

Register the tunnel URL in the ElevenLabs dashboard **before** placing a test
call. The signature check enforces a 300-second timestamp tolerance, so a
webhook that arrives after a long delay is rejected rather than replayed.

### Clerk — frontend

```bash
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/signIn
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/signUp
NEXT_PUBLIC_CLERK_SIGN_IN_FORCE_REDIRECT_URL=/dashboard
NEXT_PUBLIC_CLERK_SIGN_UP_FORCE_REDIRECT_URL=/dashboard
```

The two `FORCE_REDIRECT` values are not optional decoration. The `<SignIn>`
component already passes `forceRedirectUrl`, but those props only govern flows
that finish inside the embedded component — a flow completing on the hosted
Account Portal or an OAuth callback ignores them and uses the instance
configuration instead. These are read app-wide and close that gap.

### Google Calendar — not yet

`appointments.calendar_event_id` exists in the schema; no integration code
does. Skip it until the engine can book something.

---

## Architecture decisions worth not re-litigating

### The browser never talks to Supabase

Frontend → FastAPI → Supabase, with the service role key held server-side.
`frontend/lib/supabase.ts` was deleted for this reason and should not come back
without a specific need.

Consequences that are features, not obstacles:

- `anon` and `authenticated` hold **no** table privileges, so the
  internet-facing PostgREST and Realtime endpoints reach nothing.
- Every read of patient data passes through one choke point where it can be
  audited. A browser querying Postgres directly reads PHI without anything in
  Python observing it, and there is no clean way to audit that from inside a
  policy.

Configuring Clerk as a Supabase third-party auth provider is the enabling step
for browser-side database access. It does **not** make the system more secure —
it trades the strong lock (no grants at all) for the weaker one (policies). Do
it only for a concrete feature that needs it.

### Live updates use SSE, not Supabase Realtime

Realtime solves the problem of writes arriving from many places where the
database is the only common point. Here every write goes through FastAPI —
webhooks included — so FastAPI *is* that point, and it holds the event before
Postgres has been told about it.

```
Realtime:  ElevenLabs → FastAPI → Postgres → WAL → Realtime → browser
SSE:       ElevenLabs → FastAPI ─┬→ Postgres
                                 └→ browser
```

The stream carries a name and a row id, never the row. A client that receives
one re-fetches through the ordinary audited route, so the notification path
cannot become an unaudited side channel for PHI — and `call_logs.transcript` is
exactly the PHI in question. **That property depends on `Event` keeping its
shape.** Adding a payload field is how it stops holding.

See `app/events/broker.py`.

### Defence in depth on writes

Three layers, deliberately overlapping so a bug in one is caught by another:

1. **Pydantic request models** — `extra="ignore"`, so `doctor_id` in a payload
   is dropped rather than honoured, and `Literal` types matching every DB
   `CHECK` constraint so a bad enum is a 422 naming the field, not a 500.
2. **`WRITABLE_COLUMNS`** in `app/db/tenancy.py` — a per-table **allowlist**.
   A blocklist names what is dangerous today and admits every column added
   tomorrow; that is how `referring_doctor_id` became writable in the first
   place.
3. **RLS policies** — dormant while `authenticated` holds no grants, but proven
   correct against the live database.

Every foreign key in an accepted payload is resolved through the caller's own
scope before the write. Owning the row you are writing says nothing about where
its foreign keys point.

---

## Deliberately not built

**`appointments`, `lab-orders`, `referrals`, `notifications`,
`staff-assignments`, `reports`.** These have wrappers in
`frontend/services/api.ts`, but no page or component calls any of them. Build
one when a screen needs it; unused endpoints are attack surface with no user.

**`reports`** additionally has no entry in `PATIENT_CHILD_TABLES` or
`WRITABLE_COLUMNS`, so RLS covers it but the application cannot touch it.

**`POST /api/call-logs/{id}/check`** — `checkCallStatus()` exists in `api.ts`
and nothing calls it. It would poll ElevenLabs for an in-flight call; with the
webhook and SSE working, it may never be needed.

**Marking a call reviewed.** `needs_review` and `reviewed_at` are allowlisted
so the route can be added, but the route does not exist. It belongs on its own
narrow endpoint rather than a general update — every other outcome column is
what the *provider* reported, and a client that could rewrite those could make
a call that never reached anyone look like a confirmed appointment.

---

## Known gaps

### The test suite cannot catch a missing column

`FakeSupabase` in `tests/conftest.py` accepts any column. That is precisely how
the webhook came to write nine columns that did not exist — every test passed
against a store that never validated a schema.

**Anything touching a column added by a migration must be exercised against
real Postgres before it is trusted.** The webhook write path is the current
example: `002_call_outcomes.sql` is applied and all twelve keys it writes now
resolve, but no real webhook has confirmed it.

### Single worker only

`Dockerfile` runs one uvicorn worker, which is what makes in-process event
delivery correct. Add `--workers 2` and a webhook can land on worker A while a
browser's stream is held by worker B, which never hears about it.

The fix is Postgres `LISTEN`/`NOTIFY` — no new infrastructure. `EventBroker.publish`
is the only method that changes; nothing that calls it moves. That is why
handlers call `publish` rather than touching `_subscribers` directly.

---

## What's next, in order

1. **Workflow engine.** `executeWorkflow` and the trigger path. Real design
   work, not volume: what fires a trigger, how a `call_logs` row is created
   before the call is placed, what goes into `execution_log`. Nothing currently
   creates a call log, so this is also what makes the SSE stream show anything.
2. **PDF intake.** The dashboard's upload button. Needs two decisions: which
   parsing library, and whether files go to Supabase Storage or are discarded
   after extraction. Note that `pdf_documents.uploaded_by` is set from the
   token, not the request body.
3. **The unused resources above**, when a page needs one.

Each resource in step 3 is the same ~50-line shape as
`app/api/routes/patients.py`, which is written to be copied. Step 1 is not.
