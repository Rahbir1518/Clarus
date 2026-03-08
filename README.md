# Clarus

**Automate patient outreach. Let AI do the calling.**

Clarus is a healthcare workflow automation platform that helps clinicians automate patient follow-up, lab result outreach, and appointment scheduling through event-driven workflows and AI-powered voice calls.

---

## What It Is

Clarus is a healthcare app that connects clinical events—lab results, PDF uploads, missed appointments—to automated outreach. Clinicians design workflows in a visual, no-code builder, add patients, and the system runs outreach automatically. When conditions are met, Clarus places AI voice calls via ElevenLabs, sends SMS, creates Google Calendar events, and logs everything for audit and compliance.

---

## What It Does

### Core Features

- **Visual Workflow Builder** — Drag-and-drop design of triggers, conditions, and actions. Connect nodes for lab events, patient age checks, insurance verification, lab value thresholds, and more.

- **Automated Patient Outreach** — AI voice calls (ElevenLabs + Twilio), SMS, notifications, lab orders, referrals, and staff assignments—all triggered by workflow logic.

- **Dashboard** — Live stats (calls today, answer rate, active workflows), patient list with risk levels, PDF import, and quick access to Workflow Builder, Patient Directory, and Call Logs.

- **Patient Management** — Full CRUD for patients with conditions (ICD-10/HCC), medications, RAF scoring, and Beacon AI insights for documentation gaps.

- **PDF Intake** — Upload lab reports or patient documents; the system extracts patient info and lab results, stores them, and can run workflows automatically.

- **Call Logs & Transcripts** — Execution history, call outcomes, and AI-generated transcripts for every workflow run.

### Workflow Execution Paths

1. **Manual** — Run a workflow for a selected patient from the dashboard.
2. **Lab Event** — `POST /api/lab-event` with trigger type and patient ID; matching enabled workflows run automatically.
3. **PDF Extract & Execute** — Upload a PDF with patient ID and workflow ID; data is extracted and the workflow runs with lab results in context.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Next.js 16, React 19, Auth0, React Flow, Tailwind CSS 4, shadcn/ui, Three.js |
| **Backend** | FastAPI, Pydantic, httpx |
| **Database** | Supabase (PostgreSQL) |
| **Voice AI** | ElevenLabs Conversational AI |
| **Telephony** | Twilio |
| **Calendar** | Google Calendar API |
| **PDF Parsing** | pdfplumber, regex-based extraction |

---

## System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                            │
│  Next.js 16 Frontend (Vercel) · Auth0 · React Flow · Dashboard · Patients · Calls     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │ REST API
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              API LAYER                                               │
│  FastAPI Backend (Render) · Workflow Engine · PDF Service · Webhooks                  │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
           ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
           │  Supabase    │    │  ElevenLabs  │    │  Google      │
           │  PostgreSQL  │    │  Twilio      │    │  Calendar    │
           └──────────────┘    └──────────────┘    └──────────────┘
```

### Data Flow: Lab Event → AI Call → Calendar

```
Lab System / Manual  ──►  POST /api/lab-event  ──►  FastAPI Backend
                                                          │
                                                          ├── Query enabled workflows
                                                          ├── Load patient
                                                          └── execute_workflow()
                                                                  │
                    ┌─────────────────────────────────────┼─────────────────────────────────────┐
                    ▼                                     ▼                                     ▼
             Supabase                            Workflow Engine                        ElevenLabs API
             (create call_log,                    (trigger → conditions                   (initiate outbound
              update execution_log)                → call_patient action)                   call via Twilio)
                                                                                                  │
                                                                                                  ▼
                                                                                           Patient Phone
                                                                                                  │
             ◄────────────────────────────  POST /api/elevenlabs/webhook  ◄────────────────────────┘
             (call ended, outcome)
                    │
                    ▼
             Google Calendar API (if appointment confirmed)
```

### Component Diagram

```
FRONTEND                          BACKEND                           EXTERNAL
────────                          ───────                           ────────

Auth0 Provider ──────────────►    FastAPI Router ◄──────────────►   Supabase
api.ts (fetch) ◄─────────────►    endpoints (REST)                   PostgreSQL
React Flow Builder                workflow_engine.py ◄────────────►  ElevenLabs API
Dashboard, Patients, Calls         supabase_service.py               Twilio
                                  elevenlabs_service.py              Google Calendar
                                  pdf_service.py
```

### Database Schema (Core Tables)

```
workflows          patients           call_logs
├── id             ├── id             ├── id
├── doctor_id      ├── doctor_id      ├── workflow_id
├── nodes (JSONB)  ├── name, phone    ├── patient_id
├── edges (JSONB)  ├── dob, mrn      ├── status
└── status         └── insurance      └── execution_log (JSONB)
        │                   │
        └───────────────────┼──► patient_conditions, patient_medications, pdf_documents
                            └── notifications, lab_orders, referrals, reports
```

### Deployment

- **Frontend**: Vercel (Next.js)
- **Backend**: Render (Python, uvicorn)
- **Database**: Supabase (hosted PostgreSQL)
- **Auth**: Auth0

---

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.12+
- Supabase account
- Auth0 account
- Twilio account (for voice/SMS)
- ElevenLabs account (Conversational AI)
- Google Cloud project (for Calendar API)

### Backend Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
uvicorn main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
# Create .env.local with:
# NEXT_PUBLIC_API_URL=http://localhost:8000
# NEXT_PUBLIC_AUTH0_DOMAIN=your-tenant.us.auth0.com
# NEXT_PUBLIC_AUTH0_CLIENT_ID=your-client-id
# NEXT_PUBLIC_SUPABASE_URL=...
# NEXT_PUBLIC_SUPABASE_ANON_KEY=...
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) for the frontend and [http://localhost:8000](http://localhost:8000) for the API docs.

### Environment Variables

**Backend** (see `backend/.env.example`):

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | Twilio phone number |
| `ELEVENLABS_API_KEY` | ElevenLabs API key |
| `ELEVENLABS_AGENT_ID` | ElevenLabs agent ID |
| `ELEVENLABS_PHONE_NUMBER_ID` | ElevenLabs phone number ID |
| `AUTH0_DOMAIN` | Auth0 tenant domain |
| `AUTH0_CLIENT_ID` | Auth0 application client ID |
| `AUTH0_CLIENT_SECRET` | Auth0 application client secret |
| `AUTH0_M2M_CLIENT_ID` | Auth0 M2M app client ID (for Google tokens) |
| `AUTH0_M2M_CLIENT_SECRET` | Auth0 M2M app client secret |
| `APP_BASE_URL` | Backend base URL (for webhooks) |

---

## Project Structure

```
Clarus/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── api/            # REST endpoints
│   │   ├── core/           # Config
│   │   └── services/       # Workflow engine, ElevenLabs, PDF, Supabase
│   ├── migrations/
│   ├── main.py
│   ├── requirements.txt
│   └── Procfile
├── frontend/               # Next.js frontend
│   ├── app/
│   │   ├── (app)/         # Dashboard, patients, calls, triggers, settings
│   │   ├── (auth)/        # Sign in/up
│   │   ├── (marketing)/   # Landing, about, pricing
│   │   └── (workflow)/    # Workflow builder
│   ├── components/
│   ├── services/api.ts    # Backend API client
│   └── lib/
├── render.yaml            # Render deployment config
└── README.md
```

---

## License

See [LICENSE](LICENSE) for details.
