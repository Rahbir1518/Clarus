# Clarus backend

FastAPI + Supabase/Postgres. Rebuilt from scratch on 2026-07-25; the previous
backend was deleted rather than repaired. See [AUDIT.md](../AUDIT.md) for why.

The old code is not lost — it is at commit `91382a9`:

```bash
git show 91382a9:backend/app/api/endpoints.py     # read a single file
git checkout 91382a9 -- backend                   # restore the whole tree
```

---

## What exists today

This is a foundation, not a feature-complete API. It deliberately carries no
business logic yet.

| Area | Status |
|---|---|
| Schema, all 11 tables, in version control | ✅ `migrations/000_initial_schema.sql` |
| Clerk JWT verification (RS256, JWKS, issuer + authorized party) | ✅ `app/core/security.py` |
| Tenant isolation that cannot be forgotten | ✅ `app/db/tenancy.py` |
| Fail-fast configuration | ✅ `app/core/config.py` |
| Error envelope that does not leak internals | ✅ `app/core/errors.py` |
| Patients CRUD — the reference vertical slice | ✅ `app/api/routes/patients.py` |
| ElevenLabs agent definition, in version control | ✅ `agents/appointment_confirmation.yaml` |
| ElevenLabs client + outbound calling | ✅ `app/integrations/elevenlabs/` |
| Post-call webhook, signature-verified | ✅ `app/api/routes/webhooks.py` |
| Test suite (71 tests) | ✅ `tests/` |
| Workflows, call logs, conditions, medications | ❌ not ported |
| Workflow engine, Twilio TwiML, Calendar, PDF | ❌ not ported |

---

## Running it

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate elsewhere
pip install -e ".[dev]"

cp .env.example .env            # then fill in the four required values

uvicorn app.main:app --reload   # http://localhost:8000/docs
pytest
```

Or `docker build -t clarus-backend . && docker run -p 8000:8000 --env-file .env clarus-backend`.

### Database

Apply the schema once, against a fresh Supabase project:

```bash
psql "$DATABASE_URL" -f migrations/000_initial_schema.sql
```

Migrations are numbered and additive. Never edit `000` after it has been
applied anywhere — add `001_*.sql` instead. The reason the old schema was
unrecoverable is that it only ever existed as clicks in a dashboard.

---

## The three rules this foundation exists to enforce

### 1. Identity comes from the token, never from the request

`doctor_id` used to be a query parameter. Anyone could send any value, and
`GET /api/patients` with no parameter at all returned every patient in the
database.

Now `app/core/security.py` verifies a Clerk RS256 session token against the
instance's JWKS — checking signature, issuer, expiry, not-before and the
authorized party — and the `sub` claim becomes the tenant key. `app/api/deps.py` is the only place a `TenantScope` is
built, so a handler has no way to name a tenant other than the caller.

Request bodies may still contain `doctor_id`; the frontend sends one. It is
dropped.

### 2. An unscoped query is not expressible

Isolation used to depend on every author remembering a `WHERE doctor_id = ?`.
One place forgot, and the workflow picker showed every doctor's workflows to
every user.

`TenantScope` cannot be constructed without a `doctor_id` and exposes no method
returning an unfiltered query builder. Tables are declared as either
tenant-owned (`patients`, `workflows`, `call_logs`) or patient-owned
(everything else); the latter verify the parent patient belongs to the caller
before touching a row. Passing an unregistered table raises immediately.

"Not found" and "not yours" both return 404 — a 403 would confirm that another
tenant's record exists.

### 3. Configuration failures happen at boot

`get_settings()` resolves at import in `app/main.py`. A missing
`SUPABASE_URL` or `CLERK_ISSUER` kills the process on startup rather than
producing a 500 on whichever request first needed it.

---

## ElevenLabs

You do **not** need Supabase or the rest of the backend working to start here.
The agent is configured entirely on ElevenLabs' side, and `scripts/test_call.py`
places a real call with no database involved.

### The rule that matters

**`agents/appointment_confirmation.yaml` is the source of truth. The dashboard
is a rendering of it.**

[AUDIT.md §2a](../AUDIT.md) identified the old agent as the project's single
unrecoverable dependency: its prompt, its six data-collection fields and its
Twilio binding existed only in the ElevenLabs dashboard, so losing account
access meant reconstructing it from the field names the backend happened to
read. Edit the YAML and run the sync script; don't click in the dashboard.

### Setup, in order

1. **Account + API key** — ElevenLabs → Developers → API Keys.
   Set `ELEVENLABS_API_KEY`.
2. **Phone number** — import your Twilio number under Agents → Phone Numbers
   (needs the Twilio SID and auth token). Then:
   ```bash
   python scripts/test_call.py --list-numbers
   ```
   Put the id into `ELEVENLABS_PHONE_NUMBER_ID`.
3. **Create the agent from the spec**:
   ```bash
   python scripts/sync_agent.py --dry-run   # inspect the payload
   python scripts/sync_agent.py             # create it
   ```
   It prints an agent id for `ELEVENLABS_AGENT_ID`, then reads the agent back
   and checks every declared data-collection field actually landed. That
   read-back is the point: a 200 only means the request was accepted, and an
   agent that silently collects nothing is exactly how the old system ended up
   scraping transcripts for the word "yes".
4. **Call your own phone**:
   ```bash
   python scripts/test_call.py --to +15551234567
   python scripts/test_call.py --conversation conv_abc123   # read the result
   ```
   Iterate on the prompt in the YAML, re-run `sync_agent.py`, call again.
5. **Webhook** — ElevenLabs → Webhooks → post-call transcription, pointed at
   `https://<your-host>/api/elevenlabs/webhook`. Copy the signing secret into
   `ELEVENLABS_WEBHOOK_SECRET`. Locally: `ngrok http 8000`.

### What the webhook will and will not accept

Signature verification is the *entire* access control on that route — there is
no user token. `ELEVENLABS_WEBHOOK_SECRET` being unset does not mean "skip
verification", it means every request is refused.

Rejected: unsigned requests, wrong secret, bodies altered after signing,
signatures older than `WEBHOOK_TOLERANCE_SECONDS` (replay), and far-future
timestamps. A signed payload still cannot reassign a call log to a different
`doctor_id` or `patient_id`.

Unknown conversation ids get a 204, not a 404 — a 404 would make the endpoint
an oracle for which conversations exist.

### Two old bugs designed out

- **The "yes" heuristic.** The old code matched `\byes\b` anywhere in the
  transcript, including the agent's own lines, and booked appointments patients
  had not agreed to. Confirmation is now a structured boolean the agent must
  set deliberately, and `patient_confirmed` is *nullable*: null means the call
  never established it (voicemail, wrong number), which is not the same as a
  refusal.
- **The PM guess.** The old `_resolve_time()` turned any hour below 8 into PM,
  so a patient saying "7 AM" was booked at 19:00. The agent is now instructed to
  disambiguate verbally, read the time back, and return null rather than guess.
  A confirmation without an unambiguous time sets `needs_review` instead of
  becoming an appointment.

`CallResult.is_bookable` is the only thing that should ever trigger a calendar
event. Everything else goes to `needs_review`.

---

## Adding the next resource

`app/api/routes/patients.py` is the template. To port workflows:

1. Add `app/schemas/workflow.py` with `extra="ignore"` on request models, and
   no `doctor_id` field.
2. Add `app/api/routes/workflows.py`. Take `TenantDep`; never import
   `get_supabase` in a route.
3. Keep the URL identical to what `frontend/services/api.ts` already calls.
4. Use sync `def` handlers — the Supabase client blocks, and FastAPI will run
   sync handlers in a threadpool instead of stalling the event loop.
5. Copy `tests/test_tenancy.py` and adapt it. A resource without a
   cross-tenant test is not done.

---

## What the frontend needs before it can talk to this

Two changes, both outside this directory:

1. The frontend and this backend must point at the **same Clerk instance**.
   `CLERK_ISSUER` here and `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` there come in
   matched pairs — development and production instances are separate, with
   separate signing keys, and crossing them 401s every request.

2. `frontend/services/api.ts` must send `Authorization: Bearer <token>` from
   Clerk's `getToken()`. Tokens expire after about a minute, so fetch one per
   request rather than caching it.

3. If `CLERK_AUTHORIZED_PARTIES` is set, the frontend's origin must be in it —
   Clerk puts that origin in the `azp` claim and this backend checks it.

Until both are done the frontend will receive 401s. That is the correct
behaviour, not a regression.

---

## Deployment

There is no `render.yaml` any more, on purpose. Removing it stops new
deployments; it does **not** stop a Render service that is already running from
its last build. Suspend or delete that service in the Render dashboard, and
rotate every credential it held.

The `Dockerfile` is host-agnostic and runs unprivileged. Set `ENVIRONMENT=production`
in production — it disables `/docs` and `/openapi.json`, which otherwise publish
a complete inventory of the API.
