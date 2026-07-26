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
| Auth0 JWT verification (RS256, JWKS, audience + issuer) | ✅ `app/core/security.py` |
| Tenant isolation that cannot be forgotten | ✅ `app/db/tenancy.py` |
| Fail-fast configuration | ✅ `app/core/config.py` |
| Error envelope that does not leak internals | ✅ `app/core/errors.py` |
| Patients CRUD — the reference vertical slice | ✅ `app/api/routes/patients.py` |
| Test suite (41 tests) | ✅ `tests/` |
| Workflows, call logs, conditions, medications | ❌ not ported |
| Workflow engine, ElevenLabs, Twilio, Calendar, PDF | ❌ not ported |

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

Now `app/core/security.py` verifies an Auth0 RS256 token against the tenant's
JWKS — checking signature, audience, issuer and expiry — and the `sub` claim
becomes the tenant key. `app/api/deps.py` is the only place a `TenantScope` is
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
`SUPABASE_URL` or `AUTH0_AUDIENCE` kills the process on startup rather than
producing a 500 on whichever request first needed it.

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

1. `frontend/app/providers/Auth0ProviderWrapper.tsx` must request an audience
   matching `AUTH0_AUDIENCE`. Without it Auth0 issues an opaque token instead
   of a JWT, and every request here will 401.

   ```tsx
   authorizationParams={{ audience: process.env.NEXT_PUBLIC_AUTH0_AUDIENCE, ... }}
   ```

2. `frontend/services/api.ts` must send `Authorization: Bearer <token>` from
   `getAccessTokenSilently()`. It currently sends no auth header on any of its
   ~35 calls.

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
