# Clarus — progress

Where the build actually stands. Last updated 2026-08-09.

**Four docs, four jobs.** This one tracks *what is done and what is next*.
[backend/STATUS.md](backend/STATUS.md) is the reference for *what exists and
how to run it*. [AI_CALL_SAFETY_POLICY.md](AI_CALL_SAFETY_POLICY.md) states what
the agent may and may not say, and which of those rules are enforced in code.
[REBUILD_CHECKLIST.md](REBUILD_CHECKLIST.md) is the much larger list of what a
system holding real patient data in real clinics needs — most of it is still
unticked, and that is the honest position.

Anything marked ✅ has been verified, not assumed. Where verification was not
possible, it says so.

---

## ✅ Done

### Database

- [x] Schema, all 14 tables, in version control — `migrations/000_initial_schema.sql`
- [x] Foreign keys with explicit `ON DELETE` behaviour, chosen per relationship
- [x] `CHECK` constraints on every status column
- [x] Soft delete (`deleted_at`) on clinical tables; hard delete on operational ones
- [x] Append-only audit log, enforced by trigger — holds even against the service role
- [x] Row Level Security on every table — `migrations/001_rls.sql`
- [x] Same-tenant foreign key checks, so a row you own cannot point at a row you don't
- [x] `SECURITY DEFINER` ownership predicates with pinned `search_path`
- [x] Self-check that aborts the migration if a future table has RLS off
- [x] Call outcome columns — `migrations/002_call_outcomes.sql`

**Verified against the live database:** 7/7 privilege and RLS checks return
`true`; a forged cross-tenant referral is refused with a real `42501`; 11/11
call outcome columns present.

### Auth and tenancy

- [x] Clerk JWT verification — RS256, JWKS, issuer and authorized party
- [x] Tenant key from the verified `sub`, never from a request parameter
- [x] `TenantScope` — an unscoped query is not expressible
- [x] Server-side route protection, deny-by-default — `frontend/proxy.ts`
- [x] Sign-in/sign-up redirect behaviour, including the hosted Account Portal path
- [x] Per-table write **allowlist** (`WRITABLE_COLUMNS`) replacing a blocklist
- [x] Foreign keys in payloads resolved through the caller's own scope before writing
- [x] `referring_doctor_id` / `prescriber_doctor_id` constrained to the caller
- [x] Provider-owned fields (`conversation_id`, `transcript`, `calendar_event_id`) not client-writable
- [x] Provenance (`uploaded_by`) set from the token

**Mutation-tested:** the six cross-tenant reference tests fail when the check is
removed, so they are load-bearing rather than passing incidentally.

### API

- [x] Patients CRUD — the reference slice other resources copy
- [x] Workflows CRUD
- [x] Conditions and medications, nested under a patient
- [x] Call log reads, with the transcript withheld from the list response
- [x] Audited PHI read on the call detail route
- [x] Error envelope that does not leak internals
- [x] Fail-fast configuration
- [x] `POST /api/workflows/{id}/execute` and `POST /api/lab-event`
- [x] 225 tests passing

### Workflow engine

The blocker this list has been pointing at since the rebuild started. Built in
`backend/app/engine/` — six modules, one job each, listed in
`app/engine/__init__.py`.

- [x] **What fires a trigger.** A run always names its trigger node. `execute`
      takes one explicitly, or infers it when the graph has exactly one;
      `/api/lab-event` matches `ENABLED` workflows whose trigger node type
      equals the event. Ambiguity is a 422 naming the candidates, never a guess.
- [x] **How the graph is walked.** Depth-first from the trigger, following only
      edges whose source produced a truthy branch; a conditional's `true`/`false`
      handles pick the edge. Visited nodes are tracked, so a cycle stops instead
      of dialling forever.
- [x] **The `call_logs` row is created before the call is placed** — its id is
      the run id, so a webhook arriving mid-run has something to complete. Every
      test that places a call asserts the ordering rather than assuming it.
- [x] **`execution_log` shape decided** — append-only list of steps, each with
      `node_id`, `node_type`, `label`, `status`, `message`, `at`, and optional
      `data`. `status` is one of `ok` / `skipped` / `blocked` / `parked` /
      `failed`, and the workflow builder renders exactly those.
- [x] **Park at the call, resume from the webhook.** A run that dials stops at
      `parked` and stores everything the resume needs in `execution_log` — no
      in-memory state survives a restart. The post-call webhook re-reads the
      workflow, replays what already ran, and continues past the call node,
      booking the appointment when the patient confirmed.
- [x] Resume is idempotent: a duplicate webhook delivery does not run the graph
      twice.
- [x] A workflow edited while a call was in flight refuses to resume, because
      finishing on a graph the run did not start on is worse than stopping and
      showing a person both.
- [x] Node catalogue shared with the frontend — `app/engine/catalogue.py` and
      `frontend/components/workflow/types.ts` name the same node types, and an
      unknown type fails graph parsing rather than silently doing nothing.

### AI call safety

Written before the engine, and the reason several engine decisions look
restrictive. Full text and known gaps: [AI_CALL_SAFETY_POLICY.md](AI_CALL_SAFETY_POLICY.md).

- [x] **The agent never discloses clinical results.** It says results are ready
      and books a time.
- [x] Enforced structurally, not by prompt wording: what the agent says about
      why it is calling comes from a **fixed vocabulary of reason codes**, so
      there is no free-text field on the path to a patient's ear to abuse.
      `POST /api/calls/web` was brought under the same rule — it used to accept
      200 characters of free text and speak them.
- [x] Clinical parameter names on a call node are refused outright, so a
      workflow author cannot reintroduce disclosure by naming a parameter
      `lab_result_summary`. That parameter was removed from the frontend
      catalogue too.
- [x] Anything abnormal routes to a human: once a run passes through a
      threshold's abnormal branch it is tainted, and a call node downstream of
      it is blocked rather than reworded.
- [x] Four outbound gates, all fail-closed: kill switch (`CALLS_ENABLED`,
      default **off**), phone allowlist (empty means nothing is callable),
      calling hours measured in `DEFAULT_TIMEZONE` rather than the server's
      clock, and a per-patient attempt cap over 24 hours. A run blocked before
      dialling does not consume an attempt.
- [x] Every gate has a test asserting the refusal, and the calling-hours gate was
      accidentally proven fail-closed: the whole suite's call tests failed shut
      on a machine without `tzdata`, because an unloadable zone blocks the call
      instead of falling back to UTC and ringing someone at 3am. `tzdata` is now
      a declared dependency; the refusal stays.

### Live updates

- [x] SSE stream, tenant-scoped — `GET /api/events`
- [x] In-process event broker, thread-safe publish from sync handlers
- [x] Heartbeats so proxies don't drop idle streams
- [x] Stream lifetime cap so a fresh Clerk token is re-verified
- [x] Notifications carry a row id and no row data — the stream cannot leak PHI
- [x] Webhook publishes on call completion
- [x] Calls page updates live without flashing its loading state

### Docs

- [x] `backend/STATUS.md` — endpoints, migrations, accounts, deliberate gaps
- [x] `backend/README.md` and root `README.md` status corrected
- [x] `AI_CALL_SAFETY_POLICY.md` — what the agent may say, what enforces it,
      and what is still only a promise

---

## 🔄 In progress

### ElevenLabs call path

Built but never exercised end to end.

- [x] Agent definition in version control — `backend/agents/appointment_confirmation.yaml`
- [x] API client, including outbound calling
- [x] Post-call webhook with HMAC signature verification and timestamp tolerance
- [x] Webhook publishes to the SSE stream
- [x] Something creates a `call_logs` row now: the engine does, before it dials
- [x] The webhook resumes the parked run, not just the row
- [ ] **Fire one real webhook against real Postgres.** The test suite *cannot*
      catch a missing column — `FakeSupabase` accepts anything, which is exactly
      how the webhook came to write nine columns that did not exist. `002` is
      applied and all twelve keys resolve, but nothing has confirmed it live.
      The engine writes `execution_log` and `timezone` on top of that, so this
      check now covers more than it did.
- [ ] **Place one real call end to end.** Requires the accounts below, and
      `CALLS_ENABLED=true` with your own number in `CALL_ALLOWED_NUMBERS` —
      the gates are deliberately arranged so that forgetting either one means
      no call rather than a call to a stranger.

### Accounts — needs you, not code

- [ ] Twilio account, voice-capable number purchased
- [ ] That number imported into ElevenLabs (SID + auth token go to ElevenLabs,
      never to this backend)
- [ ] `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID`, `ELEVENLABS_PHONE_NUMBER_ID`,
      `ELEVENLABS_WEBHOOK_SECRET` in `backend/.env`
- [ ] Tunnel running and its URL registered in the ElevenLabs dashboard
- [ ] `python scripts/test_call.py --to <your own number>` — costs real money

### Frontend / backend parity

- [x] Patients, patient detail, triggers, workflow builder, calls, appointments, audit log
- [ ] Dashboard PDF intake button — the only remaining 404

---

## ⬜ To do

### 1. Finish the engine's edges

The engine runs; these are the parts a test cannot settle.

- [ ] The two live checks under "ElevenLabs call path" above — one real webhook,
      one real call
- [ ] Retry a call that reached voicemail. Today the run parks, the webhook
      records "no answer", and it stops there for a person to pick up. A second
      attempt is a policy decision (how long to wait, how many times) before it
      is code, and the attempt cap already bounds it.
- [ ] `appointments` route, so the builder can show what the engine booked.
      `schedule_appointment` writes the row; nothing reads it back yet.
- [ ] Decide whether a `parked` run should ever time out. A call whose webhook
      never arrives currently stays parked forever, which is visible but never
      resolves.

### 2. PDF intake

- [ ] Choose a parsing library
- [ ] Decide whether files go to Supabase Storage or are discarded after extraction
- [ ] `POST /api/pdf/intake` and the rest of the `pdf/*` surface
- [ ] Routes for `pdf_documents` reads

### 3. Review queue

- [ ] `PATCH /api/call-logs/{id}/review` — narrow on purpose. `needs_review`
      and `reviewed_at` are already allowlisted; every *other* outcome column
      stays provider-owned, because a client that could rewrite them could make
      a call that never reached anyone look like a confirmed appointment.

### 4. Resources with no caller yet

Build each when a screen needs it. Wrappers exist in `frontend/services/api.ts`
but nothing calls them, and an unused endpoint is attack surface with no user.

- [ ] `appointments` — table exists, no route
- [ ] `lab-orders`, `referrals`, `notifications`, `staff-assignments`
- [ ] `reports` — also needs an entry in `PATIENT_CHILD_TABLES` and
      `WRITABLE_COLUMNS`; RLS covers it, the application cannot touch it
- [ ] `POST /api/call-logs/{id}/check` — may never be needed now that the
      webhook and SSE work

### 5. Google Calendar

- [ ] Decide whether appointments sync at all
- [ ] `appointments.calendar_event_id` and `timezone` already exist for it

### 6. Engineering hygiene — none of this exists yet

- [ ] CI on every PR — no `.github/workflows` at all today
- [ ] `ruff` and `mypy` configured and enforced
- [ ] Frontend tests — there are none
- [ ] `gitleaks` secret scanning, in pre-commit *and* CI
- [ ] Branch protection on `main`
- [ ] Generate the frontend API client from the OpenAPI spec instead of
      hand-writing `services/api.ts`, and CI-check for drift
- [ ] Separate `local` / `staging` / `production` environments — separate
      databases, separate keys, separate phone numbers

### 7. Before real patient data — read REBUILD_CHECKLIST.md

Not a formality, and not optional.

- [ ] Signed agreements with every vendor touching PHI, **before** building further on them
- [ ] Data residency decision — a Supabase project's region cannot be changed later
- [ ] Tenancy model: today it is `doctor_id = Clerk sub`. A multi-doctor clinic,
      coverage, or staff access needs `Organization → Users → Patients`, and
      retrofitting that is a rewrite of every table's tenant key
- [ ] Tested restore drill, not just backups
- [ ] Retention and deletion implemented as a job, not a promise

---

## Scaling notes

Not urgent, but they become wrong silently rather than loudly.

- [ ] **More than one uvicorn worker breaks live updates.** `Dockerfile` runs a
      single worker, which is what makes in-process delivery correct. Add
      `--workers 2` and a webhook can land on worker A while a browser's stream
      sits on worker B. Fix is Postgres `LISTEN`/`NOTIFY` — no new
      infrastructure, and `EventBroker.publish` is the only method that changes.
- [ ] **`FakeSupabase` validates no schema.** Anything touching a column added
      by a migration needs a real-Postgres check before it is trusted.
