-- ===========================================================================
-- Clarus — initial schema
--
-- The previous incarnation of this project had its core tables created by hand
-- in the Supabase dashboard and never captured in version control. Only the
-- secondary tables had a migration, and it opened with foreign keys to
-- patients/workflows/call_logs — tables no migration created. That schema is
-- gone. This file reconstructs the whole thing from observed code usage and is
-- now the source of truth.
--
-- Apply with:  psql "$DATABASE_URL" -f migrations/000_initial_schema.sql
-- or paste into the Supabase SQL editor.
-- ===========================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Conventions
--
-- doctor_id is TEXT, not UUID. It holds an Auth0 subject claim, which looks
-- like 'auth0|65f...' or 'google-oauth2|1179...'. It is the tenant key for the
-- entire database, and the backend derives it from a verified JWT — never from
-- a request parameter.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ===========================================================================
-- Core tenant-owned tables
-- ===========================================================================

-- patients ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patients (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id         TEXT NOT NULL,
    name              TEXT NOT NULL,
    phone             TEXT NOT NULL,

    -- The old code called patient.get("email") in four places to add the
    -- patient as a calendar attendee, but the column existed in no migration,
    -- no Pydantic model and no README schema. Patients were never actually
    -- invited to their own appointments. Present from the start now.
    email             TEXT,

    dob               DATE,
    mrn               TEXT,
    insurance         TEXT,
    primary_physician TEXT,
    last_visit        DATE,
    risk_level        TEXT NOT NULL DEFAULT 'low'
                          CHECK (risk_level IN ('low', 'medium', 'high')),
    notes             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_patients_doctor ON patients (doctor_id);
-- An MRN is only unique within a practice, not globally.
CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_doctor_mrn
    ON patients (doctor_id, mrn) WHERE mrn IS NOT NULL;

DROP TRIGGER IF EXISTS trg_patients_updated_at ON patients;
CREATE TRIGGER trg_patients_updated_at BEFORE UPDATE ON patients
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- workflows -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS workflows (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id   TEXT NOT NULL,

    -- Read as workflow.get("doctor_name") by the old engine to personalise what
    -- the voice agent says, but never created. Every AI call told patients
    -- "your doctor" instead of a name.
    doctor_name TEXT,

    name        TEXT NOT NULL,
    description TEXT,
    category    TEXT,
    status      TEXT NOT NULL DEFAULT 'DRAFT'
                    CHECK (status IN ('DRAFT', 'ENABLED', 'ARCHIVED')),
    nodes       JSONB NOT NULL DEFAULT '[]'::JSONB,
    edges       JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workflows_doctor ON workflows (doctor_id);
CREATE INDEX IF NOT EXISTS idx_workflows_doctor_status
    ON workflows (doctor_id, status);

DROP TRIGGER IF EXISTS trg_workflows_updated_at ON workflows;
CREATE TRIGGER trg_workflows_updated_at BEFORE UPDATE ON workflows
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- call_logs -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS call_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Denormalised onto the row deliberately. The old code read
    -- call_log.get("doctor_id") against a column that did not exist, and
    -- carrying the tenant key here means call logs can be scoped without a
    -- join through two nullable foreign keys.
    doctor_id       TEXT NOT NULL,

    workflow_id     UUID REFERENCES workflows (id) ON DELETE SET NULL,
    patient_id      UUID REFERENCES patients (id) ON DELETE CASCADE,
    trigger_node    TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    outcome         TEXT,
    keypress        TEXT,
    conversation_id TEXT,
    transcript      TEXT,
    execution_log   JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_call_logs_doctor   ON call_logs (doctor_id);
CREATE INDEX IF NOT EXISTS idx_call_logs_workflow ON call_logs (workflow_id);
CREATE INDEX IF NOT EXISTS idx_call_logs_patient  ON call_logs (patient_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_call_logs_conversation
    ON call_logs (conversation_id) WHERE conversation_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_call_logs_updated_at ON call_logs;
CREATE TRIGGER trg_call_logs_updated_at BEFORE UPDATE ON call_logs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ===========================================================================
-- Patient-owned child tables
--
-- These carry no doctor_id. Ownership resolves through patient_id, and the
-- backend verifies the parent patient belongs to the caller before touching
-- them (see app/db/tenancy.py).
-- ===========================================================================

CREATE TABLE IF NOT EXISTS patient_conditions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id   UUID NOT NULL REFERENCES patients (id) ON DELETE CASCADE,
    icd10_code   TEXT NOT NULL,
    description  TEXT NOT NULL,
    hcc_category TEXT,
    raf_impact   NUMERIC(6, 3),
    status       TEXT NOT NULL DEFAULT 'active',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_patient_conditions_patient
    ON patient_conditions (patient_id);

DROP TRIGGER IF EXISTS trg_patient_conditions_updated_at ON patient_conditions;
CREATE TRIGGER trg_patient_conditions_updated_at BEFORE UPDATE ON patient_conditions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE IF NOT EXISTS patient_medications (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients (id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    dosage     TEXT,
    frequency  TEXT,
    route      TEXT,
    prescriber TEXT,
    start_date DATE,
    end_date   DATE,
    status     TEXT NOT NULL DEFAULT 'active',
    notes      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_patient_medications_patient
    ON patient_medications (patient_id);

DROP TRIGGER IF EXISTS trg_patient_medications_updated_at ON patient_medications;
CREATE TRIGGER trg_patient_medications_updated_at BEFORE UPDATE ON patient_medications
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ===========================================================================
-- Secondary tables (carried forward from the old 001_create_new_tables.sql,
-- which is the only schema artefact that survived)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS notifications (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID REFERENCES patients (id) ON DELETE CASCADE,
    recipient  TEXT NOT NULL,
    message    TEXT NOT NULL,
    priority   TEXT NOT NULL DEFAULT 'normal',
    status     TEXT NOT NULL DEFAULT 'unread',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS lab_orders (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id   UUID REFERENCES patients (id) ON DELETE CASCADE,
    test_type    TEXT NOT NULL,
    priority     TEXT NOT NULL DEFAULT 'routine',
    status       TEXT NOT NULL DEFAULT 'pending',
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS referrals (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id   UUID REFERENCES patients (id) ON DELETE CASCADE,
    specialty    TEXT NOT NULL,
    reason       TEXT NOT NULL,
    urgency      TEXT NOT NULL DEFAULT 'routine',
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS staff_assignments (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id   UUID REFERENCES patients (id) ON DELETE CASCADE,
    staff_id     TEXT NOT NULL,
    task_type    TEXT NOT NULL,
    due_date     DATE,
    status       TEXT NOT NULL DEFAULT 'assigned',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID REFERENCES workflows (id) ON DELETE SET NULL,
    patient_id  UUID REFERENCES patients (id) ON DELETE CASCADE,
    call_log_id UUID REFERENCES call_logs (id) ON DELETE SET NULL,
    report_data JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pdf_documents (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id   UUID REFERENCES patients (id) ON DELETE CASCADE,
    filename     TEXT NOT NULL,
    file_url     TEXT,
    page_count   INTEGER,
    raw_text     TEXT,
    patient_info JSONB NOT NULL DEFAULT '{}'::JSONB,
    lab_results  JSONB NOT NULL DEFAULT '[]'::JSONB,
    tables_data  JSONB NOT NULL DEFAULT '[]'::JSONB,
    uploaded_by  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notifications_patient      ON notifications (patient_id);
CREATE INDEX IF NOT EXISTS idx_lab_orders_patient         ON lab_orders (patient_id);
CREATE INDEX IF NOT EXISTS idx_referrals_patient          ON referrals (patient_id);
CREATE INDEX IF NOT EXISTS idx_staff_assignments_patient  ON staff_assignments (patient_id);
CREATE INDEX IF NOT EXISTS idx_staff_assignments_staff    ON staff_assignments (staff_id);
CREATE INDEX IF NOT EXISTS idx_reports_workflow           ON reports (workflow_id);
CREATE INDEX IF NOT EXISTS idx_reports_patient            ON reports (patient_id);
CREATE INDEX IF NOT EXISTS idx_pdf_documents_patient      ON pdf_documents (patient_id);


-- ===========================================================================
-- Row Level Security
--
-- Read this before assuming you are protected. The backend connects with the
-- Supabase service role key, and that role BYPASSES RLS on every table. These
-- policies therefore constrain nobody today — real isolation comes from
-- app/db/tenancy.py, which makes an unscoped query something you cannot
-- express.
--
-- RLS is enabled anyway, deny-by-default, so that the day anything connects
-- with the anon key or a user JWT (a Supabase-side edge function, a direct
-- browser client, an analytics tool) it gets nothing rather than everything.
-- That is the failure mode worth pre-empting.
-- ===========================================================================

ALTER TABLE patients            ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflows           ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_logs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_conditions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_medications ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications       ENABLE ROW LEVEL SECURITY;
ALTER TABLE lab_orders          ENABLE ROW LEVEL SECURITY;
ALTER TABLE referrals           ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_assignments   ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports             ENABLE ROW LEVEL SECURITY;
ALTER TABLE pdf_documents       ENABLE ROW LEVEL SECURITY;

-- No permissive policies are defined. With RLS enabled and zero policies,
-- every non-superuser, non-bypassing role is denied. Add scoped policies here
-- if and when a non-service-role client is introduced.

COMMIT;
