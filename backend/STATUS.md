# Clarus backend — status, setup, and what's next

Current as of 2026-08-09. Companion to [README.md](README.md), which explains
*how* the foundation works; this file records *what is built*, *what you must
run*, and *what is deliberately missing*.

What the AI agent may and may not say is its own document:
[../AI_CALL_SAFETY_POLICY.md](../AI_CALL_SAFETY_POLICY.md). Read it before
changing anything under `app/engine/`.

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
| `POST` | `/api/workflows/{workflow_id}/execute` — runs the graph |
| `POST` | `/api/lab-event` — trigger simulation; runs every matching `ENABLED` workflow |
| `GET` | `/api/call-logs`, `/api/call-logs/{call_log_id}` |
| `POST` | `/api/calls/web`, `/api/calls/web/{call_log_id}/bind` |
| `GET` | `/api/events` — SSE stream |
| `POST` | `/api/elevenlabs/webhook` — signature-authenticated |

225 tests, all passing.

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

### The run row is the run's memory

`app/engine/runner.py` creates the `call_logs` row **before** it dials, and the
row id *is* the run id. Everything the run knows lives in
`call_logs.execution_log`; the engine holds no state between requests.

That is what makes a call survivable. A call takes minutes and ends in a webhook
arriving at a process that may have restarted since — so the run stops at the
call node with status `parked`, and the webhook re-reads the workflow, replays
the steps already logged, and continues past the call node. An in-memory run
would lose the patient somewhere between "dialling" and "confirmed".

Three consequences worth keeping:

- **A duplicate webhook delivery must not run the graph twice.** Resume checks
  the log for a `run.resumed` step and refuses if one is there. ElevenLabs
  retries; retries are normal, not exceptional.
- **A workflow edited mid-call refuses to resume.** The graph is fingerprinted
  at run start. Finishing on a graph the run did not start on is worse than
  stopping and showing a person both, and no copy of the original is kept.
- **`execution_log` is append-only.** Steps are added; none is rewritten. It is
  the only record of *why* a patient was called, so a step that can be edited
  after the fact is not evidence of anything.

### Everything the agent says comes from a closed set

`POST /api/calls/web` used to accept 200 characters of free text and speak them
to a patient. It no longer does: both call paths resolve what the agent says
from a fixed vocabulary of reason codes in `app/engine/policy.py`.

This is the structural version of "the agent never discloses clinical results".
A prompt instruction is a request; removing the free-text field removes the
capability. The same reasoning refuses a call node carrying a parameter named
after clinical content, and taints a run that has passed through a threshold's
abnormal branch so a downstream call is blocked rather than reworded.

Every gate that decides whether a call happens at all — kill switch, phone
allowlist, calling hours, attempt cap — fails **closed**. The calling-hours gate
is the clearest case: if the timezone cannot be loaded it blocks the call rather
than assuming UTC, which is the difference between no call and a call at 3am.
`CALLS_ENABLED` defaults to false for the same reason.

See [../AI_CALL_SAFETY_POLICY.md](../AI_CALL_SAFETY_POLICY.md), including its
known gaps — the policy is honest about what is enforced and what is still only
written down.

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

`appointments` is now the first of these with a real caller waiting: the engine's
`schedule_appointment` node writes the row when a patient confirms a time, and
nothing reads it back. That route is worth building next.

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
resolve, but no real webhook has confirmed it. The engine adds
`call_logs.execution_log`, `trigger_node`, and `timezone` to the same list — 60
engine tests pass against a store that would accept a misspelled column name
just as happily.

### No call has ever been placed by the engine

Every call path is covered by tests with a fake ElevenLabs client. That proves
the gates refuse what they should and the run parks where it should; it proves
nothing about a phone ringing. Before the first real call, set
`CALLS_ENABLED=true` with **only your own number** in `CALL_ALLOWED_NUMBERS`,
and expect the gates to refuse you at least once — that is them working.

### Single worker only

`Dockerfile` runs one uvicorn worker, which is what makes in-process event
delivery correct. Add `--workers 2` and a webhook can land on worker A while a
browser's stream is held by worker B, which never hears about it.

The fix is Postgres `LISTEN`/`NOTIFY` — no new infrastructure. `EventBroker.publish`
is the only method that changes; nothing that calls it moves. That is why
handlers call `publish` rather than touching `_subscribers` directly.

---

## What's next, in order

1. **One real webhook and one real call**, in that order. The engine is built;
   what is unproven is the two places it meets a real system — a Postgres that
   validates columns, and a phone. Both are listed under "Known gaps" above with
   what specifically to watch.
2. **`appointments` route**, so the workflow builder can show what the engine
   booked. It writes appointments today and nothing reads them.
3. **PDF intake.** The dashboard's upload button, and the last remaining 404.
   Needs two decisions: which parsing library, and whether files go to Supabase
   Storage or are discarded after extraction. Note that
   `pdf_documents.uploaded_by` is set from the token, not the request body.
4. **The other unused resources above**, when a page needs one.

Steps 2 and 4 are the same ~50-line shape as `app/api/routes/patients.py`, which
is written to be copied. Step 1 is not code at all — it is accounts, a tunnel,
and paying attention to what the first call actually does.
