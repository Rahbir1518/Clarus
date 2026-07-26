# Clarus — Ground-Up Rebuild Checklist

**Purpose:** Everything needed to rebuild this project from an empty directory, optimized for correctness and security.
**Companion doc:** [AUDIT.md](AUDIT.md) — items below marked *(prevents: …)* map to a specific failure found in the existing codebase.

---

## ⚠️ Read this first: the target is real clinics

**Decision made: this is going into clinics, with real patients and real PHI.** That settles the scope question — every item in this document is in play, including the ⚖️ ones.

**⚖️ marks a legal obligation, not a nice-to-have.** In Ontario these come from PHIPA and its regulations. They are gating: you cannot ship to a clinic without them, and clinics will ask for the paperwork before they ask for a demo.

### What "into clinics" actually means

Be clear-eyed about the shape of this. The engineering is the *smaller* half.

| | |
|---|---|
| **Realistic timeline to first paying clinic** | 9–18 months |
| **Engineering** | ~4–6 months for a solid v1 (Phases 1–10) |
| **Compliance + legal** | Runs in parallel, but has its own long poles — PIA/TRA, vendor agreements, insurance |
| **The actual long pole** | ⚠️ **Lab data access** (see Phase 5b) and clinic procurement — not code |
| **Hard prerequisite** | A real business entity, not a personal side project. Vendor accounts, insurance, and clinic contracts all require one. |

### The staging discipline

You still build in stages — you just never let real patients near an unfinished stage:

1. **Synthetic** — all development. Fake patients, your own phone number as the only callable number. Enforce this in code with an allowlist, not by being careful.
2. **Shadow** — real clinic data flowing in, **zero outbound calls**. The system decides what it *would* do and logs it; a human compares against what actually happened. This stage is how you earn a clinic's trust and how you find out your extraction logic is wrong before it costs someone something.
3. **Supervised pilot** — one clinic, one workflow, every call approved by a human before dialing.
4. **Limited production** — approval gate removed for the lowest-risk workflow only.

Most of the current codebase's problems come from a build that only ever existed at stage 1 but was structured as though stage 4 would never require anything different. Structural decisions — tenancy, audit trail, migrations, consent — must be correct from commit 1, because those are the ones you cannot retrofit.

### ⚠️ You are very likely a "health information network provider"

Under PHIPA (O. Reg. 329/04, s. 6), a service that enables multiple health information custodians to use electronic means to disclose PHI to one another carries **specific statutory duties** — and this product looks a great deal like one. If that designation applies, you are required to:

- Notify **every** custodian of any unauthorized access
- Perform, and **make available to custodians on request**, a written **Privacy Impact Assessment** and **Threat Risk Assessment**
- Provide a plain-language description of your services, including safeguards
- Make available your directives, guidelines, and policies

This is why the PIA and TRA in Phase 11 are listed as gating rather than aspirational: a clinic's privacy officer can demand them, and "we haven't done one" ends the sale. **Get a PHIPA-experienced Ontario health lawyer to confirm your status early** — it determines a meaningful chunk of your obligations, and it is much cheaper to design for than to remediate.

---

## Phase 0 — Decisions before you write any code

These are hard to reverse. Make them deliberately.

- [ ] **Decide Track A or Track B.** Write it in the README. Revisit only intentionally.
- [ ] **Decide data residency.** Ontario health data is generally expected to stay in Canada. If Track B, pick a Canadian region (e.g. Supabase `ca-central-1`) at project creation — **you cannot change a Supabase project's region later**, you'd have to migrate to a new project. *(prevents: an unfixable mistake)*
- [ ] **Confirm each vendor will sign the agreement you need**, *before* building on them:
  - [ ] Supabase — DPA available on paid plans
  - [ ] Twilio — signs BAAs; requires their HIPAA-eligible configuration
  - [ ] ElevenLabs — ⚠️ **verify this one first.** Conversational AI handling PHI needs an enterprise agreement. If they won't sign, your entire voice layer needs a different vendor and you want to know that on day 0, not month 4.
  - [ ] Hosting (Vercel / Render / Fly) — enterprise tier usually required for a BAA
- [ ] **Decide the tenancy model.** Recommendation: `Organization (clinic) → Users (with roles) → Patients belong to the org`, **not** to an individual doctor. *(prevents: the current `doctor_id = Auth0 sub` model, which makes multi-doctor clinics, coverage, and staff access impossible without a rewrite)*
- [ ] **Decide the AI call safety policy** and write it down. Strong recommendation: **the AI never discloses clinical results.** It says "your results are ready, let's book a time." Anything abnormal routes to a human. *(prevents: the current design, which pipes a `lab_result_summary` into the call script)*
- [ ] **Decide the tech stack** and stick to it (suggested stack in Phase 1).
- [ ] **Name the product once.** Use it everywhere. *(prevents: backend still calling itself "MedTrigger" in patient-facing calendar invites)*

---

## Phase 1 — Repository and tooling foundation

Do this before feature code. It is an afternoon that saves months.

- [ ] Initialize repo with a **correct** `.gitignore` (`gitignore.io` for Node + Python) *(prevents: the current root `.gitignore` being an Adobe Flash template)*
- [ ] Set up the monorepo structure:
  ```
  /apps/web        Next.js frontend
  /apps/api        FastAPI backend
  /packages/schema OpenAPI-generated TS client (see below)
  /infra           IaC, migrations, deploy config
  /docs            ADRs, runbooks, compliance artifacts
  ```
- [ ] **Generate the frontend API client from the backend's OpenAPI spec** (`openapi-typescript` + `openapi-fetch`), committed and CI-checked for drift. *(prevents: the current `types/` folder describing a `firstName`/`lastName` model that the API never used — hand-written types always rot)*
- [ ] Branch protection on `main`: no direct pushes, PR + 1 review + green CI required
- [ ] Pre-commit hooks: `ruff` (lint+format), `mypy --strict`, `eslint`, `prettier`, `tsc --noEmit`
- [ ] **Secret scanning before the first commit:** `gitleaks` in pre-commit *and* in CI. *(prevents: hardcoded Web3Forms key, hardcoded Stripe links, and any future `.env` slip)*
- [ ] CI pipeline (GitHub Actions) running on every PR:
  - [ ] Lint + typecheck (both languages)
  - [ ] Unit tests with a coverage floor (start at 60%, ratchet up)
  - [ ] Integration tests against an ephemeral Postgres
  - [ ] `gitleaks`, `pip-audit`, `npm audit`, `semgrep` (or CodeQL)
  - [ ] Migration check: migrations apply cleanly to an empty DB **and** are reversible
- [ ] Dependabot / Renovate enabled
- [ ] `requirements.in` → `pip-compile` → `requirements.txt`, or use `uv`/Poetry. Track **direct** dependencies only. *(prevents: the current 70-line `pip freeze` including `pyiceberg` and `pyroaring`, which nothing imports)*
- [ ] Set up three environments — `local`, `staging`, `production` — with **separate** databases, separate API keys, separate phone numbers. Never point staging at production data.
- [ ] Write `docs/adr/0001-*.md` recording the Phase 0 decisions and why

---

## Phase 2 — Data layer

- [ ] **Migrations from commit one.** Alembic (or Supabase CLI migrations). Every schema change is a reviewed migration file. Zero dashboard-clicking. *(prevents: the single biggest failure in the current codebase — the core schema exists only in a Supabase dashboard and is now lost)*
- [ ] `000_initial_schema` defines the complete core model:
  - [ ] `organizations` — clinic
  - [ ] `users` — `id`, `org_id`, `auth_provider_id` (the IdP `sub`), `role` enum, `email`, `full_name`, `is_active`
  - [ ] `patients` — `id`, `org_id`, demographics, **`email`** (needed for calendar invites), contact preferences
  - [ ] `patient_consents` — ⚖️ consent to contact, consent to automated calls, consent to recording; each with granted/revoked timestamps and source
  - [ ] `patient_conditions`, `patient_medications`
  - [ ] `workflows` — `id`, `org_id`, `created_by`, `name`, `status`, `definition` jsonb, **`version`**
  - [ ] `workflow_runs` — replaces the overloaded `call_logs`; one row per execution with a proper state machine
  - [ ] `call_attempts` — separate from runs; a run may produce several attempts
  - [ ] `audit_events` — append-only, see Phase 8
  - [ ] Supporting: `notifications`, `lab_orders`, `referrals`, `staff_assignments`, `reports`, `documents`
- [ ] **Every PHI-bearing table has `org_id`** and an index on it
- [ ] Foreign keys with explicit `ON DELETE` behaviour, chosen per-relationship
- [ ] `CHECK` constraints on every status/enum column — do not rely on application strings
- [ ] **Row Level Security enabled on every PHI table**, with policies keyed off a session variable (`SET LOCAL app.current_org_id`), *plus* app-layer filtering. Defense in depth. *(prevents: the current design, where the service-role key bypasses RLS entirely and tenant isolation is nothing but an optional query param)*
- [ ] Application connects as a **restricted role**, not the service role / superuser. Service-role usage confined to a separately-audited admin path, if it exists at all.
- [ ] ⚖️ Column-level encryption (pgcrypto or app-layer envelope encryption) for the highest-sensitivity fields
- [ ] Automated encrypted backups + **a documented, actually-tested restore drill**
- [ ] ⚖️ Data retention and deletion policy implemented as a job, not a promise
- [ ] Seed script generating realistic **synthetic** patients for local dev *(prevents: the temptation to copy production data into dev)*

---

## Phase 3 — Authentication, authorization, tenancy

This is where the current codebase failed hardest. Build it before any feature endpoint exists.

- [ ] Choose an IdP (Auth0, Clerk, WorkOS, or Supabase Auth) and configure an **API audience** — you need access tokens, not just an ID token. *(prevents: the current SPA config that issues no API token, making backend auth impossible to add)*
- [ ] Backend: **JWT verification middleware** — validates signature against cached JWKS, plus `iss`, `aud`, `exp`, `nbf`
- [ ] **`org_id` and `user_id` are derived from verified token claims only.** No endpoint ever accepts a tenant identifier as a parameter. Make this structurally impossible: a request-context object the handlers read from. *(prevents: `GET /api/patients?doctor_id=…` — where omitting the param dumps the entire database)*
- [ ] Deny-by-default routing: the router requires auth unless a route is explicitly decorated public. Never the reverse.
- [ ] Role-based authorization (`admin` / `physician` / `staff` / `read_only`) enforced with an explicit permission check per endpoint
- [ ] **Object-level authorization on every single fetch** — `WHERE id = ? AND org_id = ?`, always. A repository layer that makes the unscoped query unwriteable is better than discipline. *(prevents: IDOR across every `/{id}` route in the current API)*
- [ ] ⚖️ MFA required for all clinical users
- [ ] Session policy: short access-token TTL, refresh rotation, idle timeout, absolute timeout
- [ ] Frontend: **real** route protection — server-side check in `middleware.ts`, not a client-side `isAuthenticated` boolean. *(prevents: the current `(app)/layout.tsx`, which reads `isAuthenticated` and never uses it)*
- [ ] Frontend: auth token attached centrally in one API client wrapper, with automatic refresh — never per-call, never optional
- [ ] Write the auth test suite **now**: unauthenticated request → 401; wrong-org request → 404 (not 403 — don't leak existence); expired token → 401; role escalation attempt → 403. These tests are the spec.

---

## Phase 4 — API layer

- [ ] Pydantic models for **every** request and response; no raw dicts crossing the boundary
- [ ] Validation on all inputs: phone numbers (E.164), dates, enums, string lengths, file sizes and MIME types
- [ ] **Idempotency keys on every state-changing endpoint** — critically on anything that places a call. A retried request must not phone a patient twice. *(prevents: a whole class of double-call incidents the current design has no defense against)*
- [ ] Rate limiting: per-user, per-org, and per-IP, with stricter limits on call-triggering and file-upload routes
- [ ] CORS: explicit origin allowlist, `allow_origin_regex` if you need preview deployments. Verify it actually matches what you think. *(prevents: the current `"https://*.vercel.app"` entry, which silently matches nothing)*
- [ ] Security headers: HSTS, CSP, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`
- [ ] Error responses never leak internals — no stack traces, no raw DB errors, no vendor error bodies to the client
- [ ] Pagination on every list endpoint (cursor-based). No unbounded `SELECT *`.
- [ ] Uploads: type/size validated, scanned, stored in private object storage with short-lived signed URLs — **never** served from a public bucket
- [ ] API versioning (`/v1/`) from the start
- [ ] OpenAPI spec is the contract; frontend client is generated from it in CI

---

## Phase 5 — External integrations

Build each one behind an interface you own, so a vendor swap is a day and not a quarter.

**All integrations**
- [ ] Every credential from a secret manager (Doppler, AWS Secrets Manager, or platform env vars). Never in code, never in the repo, never in a `.env` that could be committed. *(prevents: hardcoded Web3Forms key + Stripe links)*
- [ ] Documented rotation procedure and a rotation schedule
- [ ] Timeouts, retries with exponential backoff and jitter, and a circuit breaker on every outbound call
- [ ] Each vendor wrapped in an internal interface (`VoiceProvider`, `CalendarProvider`) — no vendor SDK types leaking into business logic

**Webhooks (inbound)**
- [ ] **Signature verification on every webhook**, before parsing the body — Twilio `X-Twilio-Signature`, ElevenLabs webhook secret, Stripe signature. Reject unsigned requests. *(prevents: anyone POSTing `patient_confirmed: true` to fabricate appointments)*
- [ ] Replay protection (timestamp window + seen-event-ID cache)
- [ ] Webhook handlers are idempotent — providers will deliver twice
- [ ] Return 2xx fast; do the real work in the queue

**Voice / AI calls**
- [ ] ⚖️ Consent verified in-code immediately before dialing — no consent row, no call
- [ ] ⚖️ Do-not-call list checked on every attempt
- [ ] Calling-hours window enforced in the patient's timezone
- [ ] Attempt caps and cooldowns per patient
- [ ] ⚖️ The agent discloses it is an automated assistant at call start
- [ ] ⚖️ The agent never states clinical results (per your Phase 0 policy)
- [ ] Clear escalation path to a human at any point in the call
- [ ] **The agent's prompt and data-collection schema live in version control** and are deployed to the vendor via API or IaC. *(prevents: the current situation, where the entire agent config exists only in a dashboard and is unrecoverable if account access is lost)*
- [ ] Structured outcome fields defined by you and asserted on — with an explicit failure state, not silent transcript-scraping fallbacks. *(prevents: the current regex heuristic that matches a bare "yes" anywhere in a transcript, including the agent's own lines, and books appointments patients never agreed to)*
- [ ] Recording/transcript storage: ⚖️ consented, encrypted, retention-limited

**Calendar**
- [ ] Store and use the **refresh token**; exchange for access tokens on demand. *(prevents: the current design reading a stale IdP access token from Auth0, which expires ~1h after login and silently breaks every calendar event)*
- [ ] Timezone stored per-organization, used consistently for parsing and event creation. Never hardcode. *(prevents: the current Toronto-parse / New\_York-write mismatch)*
- [ ] Handle token revocation gracefully with a re-consent prompt

---

## Phase 5b — ⚠️ Clinical data sources (the real long pole)

**Address this before writing much else.** The entire product premise is "a lab result arrives → a workflow fires." Right now that event comes from a human uploading a PDF. In a clinic, that is not where lab results live, and a product that requires staff to manually upload PDFs to trigger "automation" has largely defeated its own value proposition.

This question determines whether the product is viable, so answer it early.

- [ ] **Decide where clinical events actually come from.** Realistic options in Ontario:
  - [ ] **OLIS** (Ontario Laboratories Information System) — the provincial lab repository. Access is governed by Ontario Health and requires formal agreements, conformance testing, and a demonstrated PHIPA-compliant posture. High effort, high payoff, long lead time. **Start the conversation with Ontario Health early — this is measured in quarters.**
  - [ ] **Direct EMR integration** — clinics run OSCAR, TELUS PS Suite, Accuro (QHR), or Oscar Pro. Each has its own integration story, partner program, and gatekeeping. Pick your first target EMR based on which clinics you can actually reach.
  - [ ] **HL7 v2 feeds** direct from a lab (LifeLabs, Dynacare) — clinic-mediated, often the most tractable starting point
  - [ ] **PDF/manual upload** — acceptable as a *fallback* and for pilots; not a foundation
- [ ] Model clinical events as **HL7 v2 or FHIR resources internally**, whatever the source. Write adapters per source into one canonical internal event. *(prevents: coupling the entire workflow engine to a regex-parsed PDF shape)*
- [ ] Build the ingestion path idempotently — labs resend, EMRs replay
- [ ] ⚖️ Confirm your legal basis for receiving each feed, per source
- [ ] Reconciliation: detect missed or out-of-order results; never silently drop a clinical event
- [ ] Decide the write-back story — does a booked appointment land in the clinic's EMR schedule, or only Google Calendar? **Clinics schedule in their EMR.** A calendar-only integration will read as a toy to them. This is likely a v1 requirement, not v2.

---

## Phase 5c — Clinic deployment and procurement

Engineering-adjacent, but it gates revenue and it shapes the product.

- [ ] Incorporate. Vendor BAAs, insurance, and clinic contracts all require a company.
- [ ] Move every vendor account to company ownership with ≥2 admins *(prevents: the exact situation this project is now in — see [AUDIT.md](AUDIT.md) §2a)*
- [ ] Prepare the **security questionnaire packet** clinics will ask for, before they ask:
  - [ ] PIA and TRA summaries
  - [ ] Architecture and data-flow diagram
  - [ ] Subprocessor list with data residency per vendor
  - [ ] Incident response plan
  - [ ] Proof of cyber liability insurance
  - [ ] SOC 2 Type II, or a credible dated roadmap to it
- [ ] Draft the customer agreement + BAA/DPA **you** offer clinics (you are the processor here) — lawyer-drafted
- [ ] Per-clinic onboarding runbook: consent capture, staff training, escalation contacts, go-live checklist
- [ ] Unit economics per call (ElevenLabs + Twilio + infra) modelled against your pricing. The current pricing page's "$49 / 50 calls" was never checked against real cost — verify margin before quoting anyone.
- [ ] Support model: hours, SLA, on-call. Clinics will call you when a patient is confused.
- [ ] Find your **design partner clinic** early — ideally one with a physician willing to co-design and run the shadow stage. One engaged clinic is worth more than ten cold pitches.

---

## Phase 6 — Workflow engine

- [ ] Workflow definitions are **versioned and immutable once run.** A run pins the version it executed. *(prevents: editing a workflow and losing the ability to explain what actually happened during a past run — an audit problem, not just an engineering one)*
- [ ] Validate the graph on save: exactly one reachable trigger, no orphan nodes, no cycles, all required params present. Reject invalid graphs at write time, not run time.
- [ ] **Durable execution.** A run is a database-backed state machine advanced by queue workers (Postgres-backed queue, Redis+arq, or Inngest/Trigger.dev). *(prevents: the current `asyncio.create_task` poller holding 20 minutes of state in process memory, which a deploy or a second worker silently destroys — patient confirms, no event is ever created)*
- [ ] Every step is idempotent and independently retryable, with a dead-letter queue
- [ ] **A failed step halts its branch.** Explicit success/failure/skip semantics per node type. *(prevents: "generate transcript" and "send summary" running after a call that never connected)*
- [ ] Steps that wait on the outside world are genuinely asynchronous — the run parks and resumes on webhook or timer. *(prevents: `generate_transcript` fetching a transcript milliseconds after dialing, so it can never succeed)*
- [ ] The trigger-type filter parameter is actually honoured *(prevents: `trigger_node_type` being accepted, documented, and ignored)*
- [ ] Per-run execution log with structured, queryable steps
- [ ] Global kill switch: halt all outbound communication instantly, per-org and system-wide
- [ ] ⚖️ Human approval gate for any workflow branch touching abnormal results

---

## Phase 7 — Document/PDF processing

- [ ] Treat every upload as hostile: size caps, page caps, timeouts, and parse in an isolated worker — not in the web process
- [ ] **Do not use loose regex for clinical values.** Either a real document-understanding model with confidence scores, or structured HL7/FHIR ingestion. *(prevents: the current `[A-Za-z\s]+? \d+` pattern that will happily read a fax number or page count as a lab result — and then branch clinical logic on it)*
- [ ] Every extracted clinical value carries a confidence score
- [ ] **Nothing extracted drives a patient-facing action without human confirmation** below a high confidence threshold
- [ ] Extraction results are reviewable and correctable in the UI, with corrections audited
- [ ] Parse the document once per upload

---

## Phase 8 — Observability and operations

- [ ] **Structured logging with PHI redaction at the logger level**, not by convention. Names, phone numbers, MRNs, transcripts, and vendor analysis blobs must never reach your log aggregator. *(prevents: the current code logging full transcripts and `analysis` payloads to stdout — which puts PHI into Render's log storage and is itself a reportable breach)*
- [ ] Correlation IDs threaded request → job → webhook
- [ ] ⚖️ **Audit trail as a first-class feature.** Append-only `audit_events`: who accessed *which patient record*, when, from where, and what changed. PHIPA requires this. *(prevents: the current "Audit Log" page, which just re-renders call logs and records no access events at all)*
- [ ] Audit log is tamper-evident (append-only grants, ideally hash-chained) and separately retained
- [ ] Error tracking (Sentry) configured with PHI scrubbing **verified**, not assumed
- [ ] Uptime and health checks; alerting on call-failure rate, queue depth, webhook failures, auth failures
- [ ] Dashboards: runs started/completed/failed, calls placed, confirmation rate, cost per call
- [ ] Runbooks in `/docs`: credential rotation, vendor outage, restore-from-backup, ⚖️ breach response
- [ ] ⚖️ Breach notification procedure with named owner and the IPC Ontario reporting path

---

## Phase 9 — Frontend

- [ ] Server-side auth enforcement in `middleware.ts`; client checks are UX only, never security
- [ ] All data access through the generated, typed API client
- [ ] No secrets in `NEXT_PUBLIC_*`. Audit what's actually exposed in the bundle. *(prevents: shipping a Supabase client the app never used, alongside publicly-exposed keys)*
- [ ] Every list view scoped to the caller's org — verify by request inspection, not by trusting the UI. *(prevents: the current "Load Workflow" modal calling `listWorkflows()` with no filter, showing every doctor's workflows to every user)*
- [ ] Loading, empty, and **error** states on every async view — errors surfaced, never swallowed by a bare `catch {}`
- [ ] No orphaned routes: every page reachable from navigation, or deleted. *(prevents: `/triggers` — the only place to enable a workflow — being absent from the sidebar)*
- [ ] No stub pages shipped to production. Feature-flag them or leave them out.
- [ ] Destructive actions require typed confirmation and are audited
- [ ] Accessibility pass (keyboard nav, contrast, labels, screen-reader) — a legal expectation for healthcare software under AODA in Ontario
- [ ] Auto-logout on idle with a warning modal
- [ ] Session-scoped caching only; nothing PHI in `localStorage`

---

## Phase 10 — Testing strategy

- [ ] Unit tests for all business logic: the workflow engine, date/time resolution, consent checks, permission checks
- [ ] **Property-based tests for date/time parsing** — this is where subtle disasters live. *(prevents: "7 AM" silently becoming 19:00 via a blanket assume-PM rule)*
- [ ] Integration tests against a real ephemeral Postgres with RLS **on**
- [ ] **A dedicated multi-tenant isolation test suite**: org A can never see, modify, or enumerate org B's anything. Run it against every endpoint, generatively.
- [ ] Contract tests for each external vendor, plus recorded fixtures for offline runs
- [ ] Webhook tests including invalid-signature and replay cases
- [ ] End-to-end happy path in CI with all vendors stubbed
- [ ] Load test the call path — know your throughput ceiling before a clinic finds it
- [ ] ⚖️ Third-party penetration test before any real patient data
- [ ] A staging environment where calls go to a test number, wired to a real ElevenLabs test agent

---

## Phase 11 — ⚖️ Compliance artifacts (Track B)

Not code, but genuinely gating. Start these in parallel with Phase 1 — the legal timeline is longer than the engineering one.

- [ ] Privacy Impact Assessment (PIA) — expected for Ontario health information custodians
- [ ] Threat Risk Assessment (TRA)
- [ ] Signed DPAs/BAAs with every vendor touching PHI
- [ ] Record of Processing Activities — what data, why, where it lives, how long
- [ ] Patient-facing privacy notice and consent language, reviewed by a lawyer
- [ ] Internal security policy: access control, onboarding/offboarding, incident response
- [ ] **Offboarding checklist** — revoke IdP, rotate every shared credential, transfer vendor account ownership. *(prevents: exactly the situation this project is in now)*
- [ ] Staff privacy training with completion records
- [ ] Cyber liability insurance
- [ ] Legal review of the automated-calling model against CASL and PHIPA
- [ ] Ownership of every vendor account under a **company** identity, never a personal one, with at least two admins

---

## Phase 12 — Pre-launch gate

Do not go live until every line is checked.

- [ ] All Phase 3 auth tests green
- [ ] Multi-tenant isolation suite green
- [ ] ⚖️ Pen test complete, criticals and highs remediated
- [ ] Secret scan clean across **full git history**, not just `HEAD`
- [ ] Every credential rotated from its development value
- [ ] Backup restore drill performed and documented
- [ ] Kill switch tested in staging
- [ ] Logs verified PHI-free by inspection of real staging output
- [ ] Rate limits verified under load
- [ ] ⚖️ All agreements signed
- [ ] On-call rotation and escalation path defined
- [ ] Rollback plan documented and rehearsed

---

## Suggested build order

Roughly sequential; some parallelism is obvious.

Three tracks running in parallel. The compliance and clinical-access tracks have longer lead times than the engineering track, so they start on day 1 even though they finish last.

```
ENGINEERING                          COMPLIANCE (⚖️)           CLINICAL ACCESS (⚠️)
─────────────────────────────────    ──────────────────────    ─────────────────────────
0. Phase 0 decisions                 Incorporate               Scope OLIS / EMR options
1. Phase 1 repo/CI/secret-scan       Engage health lawyer      Contact Ontario Health
2. Phase 2 schema/migrations/RLS     Confirm HINP status       Pick first target EMR
3. Phase 3 auth+tenancy+tests   ←──  Vendor DPAs/BAAs          Find design-partner clinic
4. Phase 4 API, one resource E2E     Start PIA                 Negotiate feed access
5. Phase 8 logging + audit trail     Start TRA                 Build source adapters
6. Phase 9 frontend + real guards    Privacy notice/consent    ── SHADOW STAGE ──
7. Phase 6 engine, no-op nodes       Security policy set       Validate against reality
8. Phase 5 integrations, one by one  Staff training            EMR write-back
9. Phase 7 document processing       Insurance                 ── SUPERVISED PILOT ──
10. Phase 10 test hardening          Pen test                  ── LIMITED PRODUCTION ──
    (continuous, not a phase)        Questionnaire packet
11. Phase 12 launch gate  ←────────  All agreements signed
```

**Ordering principle for the engineering track:** auth, tenancy, migrations, and audit logging are load-bearing. Every one is cheap on day 1 and brutally expensive to retrofit — precisely the lesson the current codebase teaches. Build those four before the first feature and most of the audit findings become structurally impossible rather than merely fixed.

**Ordering principle overall:** start the slow, external-dependency work immediately. Vendor agreements, Ontario Health conversations, a PIA, and finding a design-partner clinic all take months of *waiting*, and none of it is blocked by your code being finished. The common failure mode is building for six months and only then discovering that your voice vendor won't sign a BAA, or that lab data access takes three quarters to arrange.
