<p align="center">
  <strong>Clarus</strong>
</p>

<p align="center">
  Healthcare workflow automation platform — AI-powered patient outreach, lab follow-up, and appointment scheduling.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Next.js-16-black?logo=next.js" alt="Next.js" />
  <img src="https://img.shields.io/badge/React-19-blue?logo=react" alt="React" />
  <img src="https://img.shields.io/badge/FastAPI-0.135-009688?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?logo=supabase" alt="Supabase" />
  <img src="https://img.shields.io/badge/ElevenLabs-ConvAI-000?logo=elevenlabs" alt="ElevenLabs" />
  <img src="https://img.shields.io/badge/Twilio-Voice%2FSMS-F22F46?logo=twilio" alt="Twilio" />
  <img src="https://img.shields.io/badge/Google-Calendar-4285F4?logo=google" alt="Google Calendar" />
  <img src="https://img.shields.io/badge/Clerk-Auth-6C47FF?logo=clerk" alt="Clerk" />
</p>

---

> ### ⚠️ Status: backend rebuild in progress (as of 2026-07-25)
>
> The backend was deleted and is being rebuilt from scratch. See
> [AUDIT.md](AUDIT.md) for why, and [backend/README.md](backend/README.md) for
> what exists today.
>
> **Sections below marked _(pre-rebuild)_ describe the old backend and are kept
> as a record of intended behaviour, not as a description of current code.**
> The frontend sections are current.
>
> What is real right now: the schema in
> [backend/migrations/000_initial_schema.sql](backend/migrations/000_initial_schema.sql),
> Clerk JWT verification, enforced tenant isolation, and patients CRUD.
> Everything else — workflows, call logs, the workflow engine, ElevenLabs,
> Twilio, Google Calendar and PDF processing — is not yet ported.
>
> The old backend remains readable at commit `91382a9`.

---

## Overview

Clarus helps clinicians automate patient follow-up through:

- **Visual workflow builder** — Drag-and-drop design of triggers, conditions, and actions (React Flow)
- **AI voice calls** — ElevenLabs Conversational AI + Twilio for outbound patient outreach
- **Event-driven execution** — Lab events, PDF uploads, or manual triggers run workflows automatically
- **Patient management** — Full CRUD with ICD-10/HCC conditions, medications, RAF scoring, Beacon AI insights
- **PDF intake** — Extract patient info and lab results from documents; run workflows with extracted data
- **Google Calendar** — Create appointments when patients confirm during AI calls
- **Audit trail** — Execution logs, call transcripts, and reports for every workflow run

The frontend connects to the FastAPI backend via REST. The workflow engine walks the graph, evaluates conditions, and dispatches actions (call patient, send SMS, create lab order, etc.). ElevenLabs webhooks update call logs and trigger calendar events.

---

## System Architecture

```mermaid
graph TB
    subgraph Frontend["FRONTEND — Next.js 16 + React 19"]
        direction TB
        Landing["/ Landing, About, Features, Pricing"]
        Auth["(auth) Clerk Sign-In / Sign-Up"]

        subgraph Dashboard["App Routes — Protected by Clerk middleware"]
            DashView["/dashboard — Stats, Patients, PDF Import"]
            Patients["/patients — Patient Directory"]
            PatientDetail["/patients/[id] — Profile, Conditions, Meds"]
            Workflow["/workflow — Workflow Builder"]
            Triggers["/triggers — Workflow Triggers"]
            Calls["/calls — Call Logs"]
            Appointments["/appointments — Calendar"]
            AuditLog["/audit-log — Activity"]
            Settings["/settings — Profile, Notifications"]
        end

        subgraph FComponents["Components"]
            WorkflowBuilder["WorkflowBuilder — React Flow"]
            NodePalette["NodePalette"]
            TriggerNode["TriggerNode, ActionNode, ConditionalNode"]
            EndpointNode["EndpointNode"]
            Sidebar["Sidebar, Topbar"]
            Hero["Hero, Features, CTA"]
        end

        subgraph FServices["Services"]
            ApiClient["api.ts — fetch to backend"]
        end
    end

    subgraph Backend["BACKEND — FastAPI + Python"]
        direction TB
        subgraph API["REST Endpoints"]
            PatientsAPI["/api/patients"]
            WorkflowsAPI["/api/workflows"]
            ExecuteAPI["/api/workflows/{id}/execute"]
            LabEventAPI["/api/lab-event"]
            CallLogsAPI["/api/call-logs"]
            PDFAPI["/api/pdf/*"]
            WebhookAPI["/api/elevenlabs/webhook"]
            TwilioAPI["/api/twilio/voice, gather"]
        end

        subgraph Services["Services"]
            WorkflowEngine["Workflow Engine — graph traversal"]
            SupabaseSvc["Supabase Service — CRUD"]
            ElevenLabsSvc["ElevenLabs Service — outbound calls"]
            PDFSvc["PDF Service — extraction"]
            CalendarSvc["Google Calendar Service"]
        end
    end

    subgraph External["EXTERNAL SERVICES"]
        Supabase["Supabase PostgreSQL"]
        ElevenLabs["ElevenLabs ConvAI API"]
        Twilio["Twilio Voice/SMS"]
        GoogleCal["Google Calendar API"]
        ClerkExt["Clerk"]
    end

    Auth -.-> ClerkExt
    ApiClient -->|REST| API
    WorkflowBuilder -->|save nodes/edges| WorkflowsAPI
    DashView -->|list patients, workflows, calls| PatientsAPI
    LabEventAPI --> WorkflowEngine
    ExecuteAPI --> WorkflowEngine
    WorkflowEngine --> SupabaseSvc
    WorkflowEngine --> ElevenLabsSvc
    WorkflowEngine --> CalendarSvc
    WebhookAPI --> SupabaseSvc
    WebhookAPI --> CalendarSvc

    SupabaseSvc -.-> Supabase
    ElevenLabsSvc -.-> ElevenLabs
    Twilio -.-> ElevenLabs
    CalendarSvc -.-> GoogleCal
```

---

## Tech Stack

| Layer | Technologies | How We Use It |
|-------|--------------|---------------|
| **Frontend** | Next.js 16, React 19, TypeScript 5, Tailwind CSS 4 | App Router with protected routes, server/client components, responsive UI |
| **Workflow UI** | React Flow (@xyflow/react), Dagre | Visual workflow builder with drag-and-drop nodes and edges |
| **Authentication** | Clerk (`@clerk/nextjs`) | Sign-in/sign-up, `user.id` as `doctor_id` for data scoping, `middleware.ts` route protection |
| **Backend** | FastAPI, Uvicorn, Python 3.12+ | REST API, Pydantic schemas, Clerk JWT verification, tenant-scoped data access |
| **Database** | Supabase (PostgreSQL) | Workflows, patients, conditions, medications, call_logs, pdf_documents |
| **Voice AI** | ElevenLabs Conversational AI | Outbound AI voice calls via Twilio; webhook for call outcomes |
| **Telephony** | Twilio | Voice calls (ElevenLabs integration), SMS fallback |
| **Calendar** | Google Calendar API | Create events when patients confirm appointments during AI calls |
| **PDF Parsing** | pdfplumber, pdfminer.six, pypdfium2 | Extract patient info, lab results, tables from medical PDFs |
| **HTTP Client** | httpx | Async requests to ElevenLabs, Google APIs |
| **UI** | shadcn/ui, Lucide React | Buttons, modals, icons across dashboard and app |
| **3D** | Three.js, React Three Fiber, Drei | Marketing page visuals (sphere, particles) |
| **Deployment** | Vercel, container | Frontend on Vercel; backend ships as a Docker image, production host not yet chosen (Render removed) |

---

## Project Structure

### Frontend

```
frontend/
├── app/                              # Next.js App Router
│   ├── layout.tsx                    # Root layout with ClerkProvider
│   ├── globals.css                   # Tailwind theme
│   ├── (auth)/                       # Auth routes
│   │   ├── signIn/[[...sign-in]]/page.tsx
│   │   └── signUp/[[...sign-up]]/page.tsx
│   ├── (marketing)/                  # Public marketing
│   │   ├── page.tsx                  # Landing
│   │   ├── about/page.tsx
│   │   ├── features/page.tsx
│   │   ├── pricing/page.tsx
│   │   └── contact/page.tsx
│   ├── (app)/                        # Protected app routes
│   │   ├── dashboard/page.tsx       # Stats, patients, PDF import, workflows
│   │   ├── patients/page.tsx        # Patient directory
│   │   ├── patients/[patientId]/page.tsx  # Patient profile, conditions, meds
│   │   ├── calls/page.tsx           # Call logs
│   │   ├── appointments/page.tsx    # Calendar view
│   │   ├── triggers/page.tsx        # Workflow triggers list
│   │   ├── triggers/[triggerId]/page.tsx
│   │   ├── triggers/new/page.tsx
│   │   ├── audit-log/page.tsx       # Activity log
│   │   └── settings/                # Profile, notifications
│   └── (workflow)/
│       └── workflow/page.tsx         # Workflow builder
├── components/
│   ├── app/                          # Sidebar, Topbar
│   ├── marketing/                   # Hero, Features, CTA, Footer
│   ├── workflow/                    # WorkflowBuilder, NodePalette, nodes
│   └── ui/                          # Button, etc.
├── services/
│   └── api.ts                       # Backend API client (fetch)
├── lib/
│   ├── supabase.ts                  # Supabase client
│   └── utils.ts
├── types/
└── middleware.ts                    # Clerk route protection (deny by default)
```

### Backend

```
backend/
├── app/
│   ├── main.py                       # FastAPI app, CORS, error handlers
│   ├── core/
│   │   ├── config.py                 # Settings; fails fast when incomplete
│   │   ├── security.py               # Clerk JWT verification (RS256 + JWKS)
│   │   └── errors.py                 # Error envelope, no internal leakage
│   ├── db/
│   │   ├── client.py                 # Supabase client
│   │   └── tenancy.py                # TenantScope — the isolation choke point
│   ├── api/
│   │   ├── deps.py                   # Only place a TenantScope is built
│   │   └── routes/
│   │       ├── health.py
│   │       └── patients.py           # Reference vertical slice
│   └── schemas/
│       └── patient.py
├── migrations/
│   └── 000_initial_schema.sql        # All 11 tables, in version control
├── tests/                            # 41 tests: auth + tenant isolation
├── Dockerfile                        # Host-agnostic; replaces render.yaml
├── pyproject.toml                    # Direct deps only
└── .env.example
```

See [backend/README.md](backend/README.md) for how to run it and how to port
the next resource.

---

## Data Flows

### 1. Lab Event → Workflow Execution → AI Call

```
Lab System / Manual Simulation
    │ POST /api/lab-event {trigger_type, patient_id}
    ▼
┌─ Backend ─────────────────────────────────────┐
│  Query enabled workflows by trigger_type       │
│  Load patient from Supabase                   │
│  execute_workflow() — graph traversal          │
│    → trigger → conditions → actions            │
│    → call_patient action                       │
│    → ElevenLabs initiate_outbound_call()       │
└───────────────────────────────────────────────┘
    │
    ▼
ElevenLabs + Twilio → Patient Phone (AI conversation)
    │
    │ POST /api/elevenlabs/webhook (call ended)
    ▼
Update call_log, create Google Calendar event if confirmed
```

### 2. PDF Extract & Execute

```
PDF Upload (lab report)
    │ POST /api/pdf/extract-and-execute {file, patient_id, workflow_id}
    ▼
┌─ Backend ─────────────────────────────────────┐
│  pdf_service: extract text + tables           │
│  Parse patient info (name, DOB, MRN, phone)   │
│  Parse lab results (test_name, value, unit)    │
│  Store in pdf_documents                        │
│  execute_workflow() with lab_results in context│
└───────────────────────────────────────────────┘
```

### 3. Manual Workflow Execution

```
Dashboard / Patient Profile
    │ POST /api/workflows/{id}/execute {patient_id}
    ▼
Workflow Engine → same flow as Lab Event
```

### 4. Twilio Voice Webhook (Inbound)

```
Patient answers call
    │ Twilio → POST /api/twilio/voice
    ▼
Return TwiML to connect to ElevenLabs
    │
    │ Twilio → POST /api/twilio/gather (if DTMF)
    ▼
Process input, return TwiML
```

---

## Routes & Protection *(pre-rebuild)*

> ✅ Now implemented. `middleware.ts` protects every route that is not
> explicitly listed as public, so protection is the default and a new route is
> covered without anyone remembering to add it. This closes
> [AUDIT.md §4](AUDIT.md), which recorded that `(app)/layout.tsx` destructured
> `isAuthenticated` and never used it — every "protected" route rendered for
> anyone. Note that this only governs which pages are served: the backend
> verifies its own token independently on every request.

| Route | Purpose | Protection (intended) |
|-------|---------|------------|
| `/` | Landing page | Public |
| `/about`, `/features`, `/pricing`, `/contact` | Marketing | Public |
| `/signIn`, `/signUp` | Auth | Public |
| `/dashboard` | Stats, patients, workflows, PDF import | Clerk |
| `/patients` | Patient directory | Clerk |
| `/patients/[id]` | Patient profile, conditions, medications | Clerk |
| `/workflow` | Workflow builder | Clerk |
| `/triggers` | Workflow triggers list | Clerk |
| `/calls` | Call logs | Clerk |
| `/appointments` | Calendar | Clerk |
| `/audit-log` | Activity log | Clerk |
| `/settings` | Profile, notifications | Clerk |

---

## REST API Endpoints

### Implemented today

All `/api/*` routes require `Authorization: Bearer <Clerk session token>` and are scoped
to the token's `sub`. A missing or invalid token is a 401; another tenant's
record is a 404.

| Endpoint | Method | Auth |
|----------|--------|------|
| `/health` | GET | Public |
| `/health/ready` | GET | Public |
| `/api/patients` | GET, POST | Required |
| `/api/patients/{id}` | GET, PUT, DELETE | Required |

### Not yet ported *(pre-rebuild)*

The routes below existed in the old backend and are the target surface for the
rebuild. The frontend still calls them, so they will be restored at the same
paths. None of them exist right now.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/patients/{id}/conditions` | GET, POST | List, create conditions |
| `/api/patients/{id}/conditions` | GET, POST | List, create conditions |
| `/api/patients/{id}/conditions/{cid}` | PUT, DELETE | Update, delete condition |
| `/api/patients/{id}/medications` | GET, POST | List, create medications |
| `/api/patients/{id}/medications/{mid}` | PUT, DELETE | Update, delete medication |
| `/api/patients/{id}/import-pdf` | POST | Import PDF to patient |
| `/api/workflows` | GET, POST | List, create workflows |
| `/api/workflows/{id}` | GET, PUT, DELETE | Get, update, delete workflow |
| `/api/workflows/{id}/execute` | POST | Execute workflow for patient |
| `/api/lab-event` | POST | Simulate lab event, run workflows |
| `/api/call-logs` | GET | List call logs |
| `/api/call-logs/{id}/check` | POST | Poll ElevenLabs for call status |
| `/api/elevenlabs/webhook` | POST | ElevenLabs post-call webhook |
| `/api/twilio/voice` | POST | Twilio voice TwiML |
| `/api/twilio/gather` | POST | Twilio gather TwiML |
| `/api/pdf/upload` | POST | Upload PDF |
| `/api/pdf/intake` | POST | PDF intake (create patient) |
| `/api/pdf/extract-and-execute` | POST | Extract + run workflow |
| `/api/pdf/documents` | GET | List PDF documents |
| `/api/pdf/documents/{id}` | GET, DELETE | Get, delete document |
| `/api/notifications` | GET | List notifications |
| `/api/lab-orders` | GET | List lab orders |
| `/api/referrals` | GET | List referrals |
| `/api/staff-assignments` | GET | List staff assignments |
| `/api/reports` | GET | List reports |
| `/api/reports/{id}` | GET | Get report |

---

## Database Schema (Core Tables)

> The authoritative schema is
> [backend/migrations/000_initial_schema.sql](backend/migrations/000_initial_schema.sql).
> The sketch below is a summary; where the two differ, the migration wins.
> Note it now includes `patients.email`, `workflows.doctor_name` and
> `call_logs.doctor_id`, which the old code read but no migration ever created.

```
workflows              patients              call_logs
├── id                 ├── id                ├── id
├── doctor_id          ├── doctor_id         ├── workflow_id
├── name               ├── name, phone       ├── patient_id
├── nodes (JSONB)      ├── dob, mrn          ├── status, outcome
├── edges (JSONB)      ├── insurance         └── execution_log (JSONB)
└── status             └── risk_level
        │                       │
        └───────────────────────┼──► patient_conditions
                                ├── patient_medications
                                ├── pdf_documents
                                ├── notifications
                                ├── lab_orders
                                ├── referrals
                                ├── staff_assignments
                                └── reports
```

---

## Environment Variables

### Frontend (`frontend/.env.local`)

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_URL` | Backend URL (default `http://localhost:8000`) |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk instance key. Must be the **same instance** as the backend's `CLERK_ISSUER` |
| `CLERK_SECRET_KEY` | Server-side only, used by `middleware.ts`. Never prefix with `NEXT_PUBLIC_` |
| `NEXT_PUBLIC_CLERK_SIGN_IN_URL` | `/signIn` — must match the route and the public matcher in `middleware.ts` |
| `NEXT_PUBLIC_CLERK_SIGN_UP_URL` | `/signUp` — same |

The `NEXT_PUBLIC_SUPABASE_*` variables are gone. `lib/supabase.ts` was deleted:
nothing imported it, and it published project credentials to the browser for a
client that was never used. All data access goes through the backend.

### Backend (`backend/.env`)

Required — the process refuses to start without all three:

| Variable | Purpose |
|----------|---------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key. Bypasses RLS; never expose to a browser |
| `CLERK_ISSUER` | Clerk Frontend API origin, no trailing slash. Both the `iss` we verify and the root of the JWKS URL |

Optional:

| Variable | Purpose |
|----------|---------|
| `ENVIRONMENT` | `production` disables `/docs` and `/openapi.json` |
| `CORS_ORIGINS` | Comma-separated exact origins |
| `CORS_ORIGIN_REGEX` | For preview deployments. `allow_origins` does exact matching and never expanded globs like `https://*.vercel.app` |

Twilio and the optional `CLERK_SECRET_KEY` are listed in
[backend/.env.example](backend/.env.example) but are not read by any code yet —
those integrations have not been ported.

---

## Getting Started

### Prerequisites

- **Node.js** 18+ and **npm**
- **Python** 3.12+
- Accounts: Supabase, Clerk, Twilio, ElevenLabs, Google Cloud

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate elsewhere
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Fill in the four required values

# Apply the schema (once, against a fresh Supabase project)
psql "$DATABASE_URL" -f migrations/000_initial_schema.sql

# Start the server
uvicorn app.main:app --reload --port 8000
# → Runs on http://localhost:8000
# → Docs at http://localhost:8000/docs

pytest                          # 41 tests
```

### Frontend

```bash
cd frontend
npm install

# Configure environment
# cp .env.example .env.local, then fill in the Clerk keys

# Start development server
npm run dev
# → Runs on http://localhost:3000
```

### Quick Test

1. Open `http://localhost:3000` → sign in via Clerk
2. Navigate to `/dashboard` → add a patient, view workflows
3. Open `/workflow` → build a workflow (trigger → condition → call patient)
4. Run workflow manually or simulate a lab event via `POST /api/lab-event`

---

## Deployment

- **Frontend**: Vercel (Next.js)
- **Backend**: container, host not yet chosen — see [backend/Dockerfile](backend/Dockerfile)
- **Database**: Supabase (hosted PostgreSQL)
- **Auth**: Clerk

> **Render has been removed.** `render.yaml` is deleted, so nothing new deploys
> there. That does **not** stop a Render service already running from its last
> build — it keeps serving until it is suspended or deleted in the Render
> dashboard, and its credentials keep working until rotated.
>
> Production will be a new, independent service built from the Dockerfile. Set
> `ENVIRONMENT=production` there to disable `/docs` and `/openapi.json`.

---

## Summary

| What | How |
|------|-----|
| **Frontend** | Next.js 16 app with Clerk, dashboard, patients, workflow builder, call logs |
| **Backend** | FastAPI with workflow engine, Supabase, ElevenLabs, Twilio, Google Calendar |
| **Workflows** | Triggers → conditions → actions; stored as nodes/edges in Supabase |
| **Execution** | Lab event, PDF upload, or manual → workflow engine → actions (call, SMS, etc.) |
| **AI Calls** | ElevenLabs ConvAI + Twilio → patient phone → webhook → call_log + calendar |
| **PDF** | pdfplumber extraction → patient + lab data → workflow context |

Clarus automates patient outreach from clinical events to AI voice calls and calendar booking.

---

## License

See [LICENSE](LICENSE) for details.
