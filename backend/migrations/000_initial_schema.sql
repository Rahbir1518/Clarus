-- ===========================================================================
-- Clarus — schema
--
-- This file is the source of truth. `schema.sql` beside it is a Supabase
-- dashboard dump kept for readability: dumps of that form carry columns and
-- constraints but no indexes, no triggers and no ON DELETE behaviour, so they
-- cannot rebuild a working database. Change the schema here, apply the file,
-- and refresh the dump afterwards if you want the snapshot to stay current.
--
-- Every statement is idempotent. Running it against the existing Supabase
-- project creates nothing that already exists and adds the indexes, triggers
-- and referential actions the dashboard-built schema is missing.
--
-- Apply with:  psql "$DATABASE_URL" -f migrations/000_initial_schema.sql
-- or paste into the Supabase SQL editor.
-- ===========================================================================

BEGIN;

-- Every name below is unqualified. Pin the schema so the tables land in
-- `public` regardless of the search_path the client happens to connect with.
SET search_path = public, pg_temp;

-- ---------------------------------------------------------------------------
-- Conventions
--
-- doctor_id is TEXT, not UUID. It holds a Clerk user id, which looks like
-- 'user_2abc...'. It is the tenant key for the entire database, and the backend
-- derives it from a verified JWT — never from a request parameter.
--
-- Rows that can carry PHI are deleted softly: a `deleted_at` timestamp rather
-- than a DELETE. PHIPA expects a record of what existed and when it was
-- removed, and a hard DELETE destroys the ability to answer that. Tables
-- without a `deleted_at` column (notifications, staff_assignments, reports)
-- are operational rather than clinical and are removed outright.
--
-- Every read path must therefore filter `deleted_at IS NULL`. The backend does
-- this inside TenantScope so no caller has to remember (see app/db/tenancy.py).
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ===========================================================================
-- Tenants
-- ===========================================================================

-- doctors -------------------------------------------------------------------
-- The tenant root. Every doctor_id elsewhere is a foreign key to this table,
-- which is what makes an orphaned record — the old backend's `'anonymous'` and
-- `'unknown'` fallbacks — impossible to insert rather than merely discouraged.
-- The backend provisions a row on first authenticated request; see
-- app/db/doctors.py.
CREATE TABLE IF NOT EXISTS doctors (
    id            TEXT PRIMARY KEY,          -- Clerk `sub`, e.g. user_2abc...
    name          TEXT NOT NULL,
    email         TEXT,
    phone         TEXT,
    npi           TEXT,
    specialty     TEXT,
    practice_name TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_doctors_updated_at ON doctors;
CREATE TRIGGER trg_doctors_updated_at BEFORE UPDATE ON doctors
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ===========================================================================
-- Core tenant-owned tables
-- ===========================================================================

-- patients ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patients (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id         TEXT NOT NULL REFERENCES doctors (id) ON DELETE RESTRICT,
    name              TEXT NOT NULL,
    phone             TEXT NOT NULL,

    -- The old code called patient.get("email") in four places to add the
    -- patient as a calendar attendee, but the column existed in no migration,
    -- no Pydantic model and no README schema. Patients were never actually
    -- invited to their own appointments.
    email             TEXT,

    dob               DATE,
    mrn               TEXT,
    insurance         TEXT,
    primary_physician TEXT,
    last_visit        DATE,
    risk_level        TEXT NOT NULL DEFAULT 'low'
                          CHECK (risk_level IN ('low', 'moderate', 'high')),
    notes             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_patients_doctor
    ON patients (doctor_id) WHERE deleted_at IS NULL;

-- An MRN is only unique within a practice, not globally. A deleted patient
-- must not block re-registration under the same MRN.
CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_doctor_mrn
    ON patients (doctor_id, mrn)
    WHERE mrn IS NOT NULL AND deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_patients_updated_at ON patients;
CREATE TRIGGER trg_patients_updated_at BEFORE UPDATE ON patients
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- workflows -----------------------------------------------------------------
-- No deleted_at: a workflow is retired by moving it to status 'ARCHIVED',
-- which keeps it referenceable from the call logs and reports it produced.
CREATE TABLE IF NOT EXISTS workflows (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id   TEXT NOT NULL REFERENCES doctors (id) ON DELETE RESTRICT,

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
    doctor_id       TEXT NOT NULL REFERENCES doctors (id) ON DELETE RESTRICT,

    workflow_id     UUID REFERENCES workflows (id) ON DELETE SET NULL,
    patient_id      UUID REFERENCES patients (id) ON DELETE SET NULL,
    trigger_node    TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    outcome         TEXT,
    keypress        TEXT,
    conversation_id TEXT,
    transcript      TEXT,
    execution_log   JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_call_logs_doctor
    ON call_logs (doctor_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_call_logs_workflow ON call_logs (workflow_id);
CREATE INDEX IF NOT EXISTS idx_call_logs_patient  ON call_logs (patient_id);

-- Load-bearing, not an optimisation. app/db/system.py resolves an inbound
-- provider webhook to exactly one call log by conversation_id; without this
-- index a duplicate conversation_id would let one webhook update two rows.
CREATE UNIQUE INDEX IF NOT EXISTS idx_call_logs_conversation
    ON call_logs (conversation_id) WHERE conversation_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_call_logs_updated_at ON call_logs;
CREATE TRIGGER trg_call_logs_updated_at BEFORE UPDATE ON call_logs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- appointments --------------------------------------------------------------
-- Carries doctor_id directly for the same reason call_logs does: an
-- appointment is listed by practice, and scoping it through patient_id would
-- mean a join on every read.
CREATE TABLE IF NOT EXISTS appointments (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id         TEXT NOT NULL REFERENCES doctors (id) ON DELETE RESTRICT,
    patient_id        UUID NOT NULL REFERENCES patients (id) ON DELETE CASCADE,
    workflow_id       UUID REFERENCES workflows (id) ON DELETE SET NULL,
    call_log_id       UUID REFERENCES call_logs (id) ON DELETE SET NULL,
    calendar_event_id TEXT,
    starts_at         TIMESTAMPTZ NOT NULL,
    ends_at           TIMESTAMPTZ,
    status            TEXT NOT NULL DEFAULT 'scheduled'
                          CHECK (status IN ('scheduled', 'confirmed', 'completed',
                                            'cancelled', 'no_show')),
    location          TEXT,
    reason            TEXT,
    notes             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at        TIMESTAMPTZ,

    CONSTRAINT appointments_ends_after_starts
        CHECK (ends_at IS NULL OR ends_at > starts_at)
);

CREATE INDEX IF NOT EXISTS idx_appointments_doctor_starts
    ON appointments (doctor_id, starts_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_appointments_patient
    ON appointments (patient_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_appointments_workflow ON appointments (workflow_id);
CREATE INDEX IF NOT EXISTS idx_appointments_call_log ON appointments (call_log_id);

-- One calendar event maps to one appointment. Without this, a retried
-- Google Calendar insert silently produces two appointment rows.
CREATE UNIQUE INDEX IF NOT EXISTS idx_appointments_calendar_event
    ON appointments (calendar_event_id) WHERE calendar_event_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_appointments_updated_at ON appointments;
CREATE TRIGGER trg_appointments_updated_at BEFORE UPDATE ON appointments
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
    status       TEXT NOT NULL DEFAULT 'documented'
                     CHECK (status IN ('documented', 'review_needed', 'pending_review')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_patient_conditions_patient
    ON patient_conditions (patient_id) WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_patient_conditions_updated_at ON patient_conditions;
CREATE TRIGGER trg_patient_conditions_updated_at BEFORE UPDATE ON patient_conditions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE IF NOT EXISTS patient_medications (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id           UUID NOT NULL REFERENCES patients (id) ON DELETE CASCADE,
    name                 TEXT NOT NULL,
    dosage               TEXT,
    frequency            TEXT,
    route                TEXT,

    -- `prescriber` is free text for an outside prescriber; the FK is set only
    -- when the prescriber is a doctor on this system.
    prescriber           TEXT,
    prescriber_doctor_id TEXT REFERENCES doctors (id) ON DELETE SET NULL,

    start_date           DATE,
    end_date             DATE,
    status               TEXT NOT NULL DEFAULT 'active'
                             CHECK (status IN ('active', 'discontinued', 'on_hold')),
    notes                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_patient_medications_patient
    ON patient_medications (patient_id) WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_patient_medications_updated_at ON patient_medications;
CREATE TRIGGER trg_patient_medications_updated_at BEFORE UPDATE ON patient_medications
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ===========================================================================
-- Operational tables
--
-- Removed outright rather than soft-deleted: none of them is a clinical record
-- in its own right, and each is reconstructible from the run that produced it.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS notifications (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID REFERENCES patients (id) ON DELETE CASCADE,
    recipient  TEXT NOT NULL,
    message    TEXT NOT NULL,
    priority   TEXT NOT NULL DEFAULT 'normal',
    status     TEXT NOT NULL DEFAULT 'unread' CHECK (status IN ('unread', 'read')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_notifications_patient ON notifications (patient_id);
CREATE INDEX IF NOT EXISTS idx_notifications_unread
    ON notifications (recipient) WHERE status = 'unread';

DROP TRIGGER IF EXISTS trg_notifications_updated_at ON notifications;
CREATE TRIGGER trg_notifications_updated_at BEFORE UPDATE ON notifications
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE IF NOT EXISTS staff_assignments (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id   UUID REFERENCES patients (id) ON DELETE CASCADE,
    staff_id     TEXT NOT NULL,
    task_type    TEXT NOT NULL,
    due_date     DATE,
    status       TEXT NOT NULL DEFAULT 'assigned'
                     CHECK (status IN ('assigned', 'in_progress', 'completed', 'cancelled')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_staff_assignments_patient
    ON staff_assignments (patient_id);
CREATE INDEX IF NOT EXISTS idx_staff_assignments_staff
    ON staff_assignments (staff_id, status);

DROP TRIGGER IF EXISTS trg_staff_assignments_updated_at ON staff_assignments;
CREATE TRIGGER trg_staff_assignments_updated_at BEFORE UPDATE ON staff_assignments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ===========================================================================
-- Clinical orders
-- ===========================================================================

CREATE TABLE IF NOT EXISTS lab_orders (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id   UUID REFERENCES patients (id) ON DELETE CASCADE,
    test_type    TEXT NOT NULL,
    priority     TEXT NOT NULL DEFAULT 'routine',
    status       TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'collected', 'completed', 'cancelled')),
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    deleted_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_lab_orders_patient
    ON lab_orders (patient_id) WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_lab_orders_updated_at ON lab_orders;
CREATE TRIGGER trg_lab_orders_updated_at BEFORE UPDATE ON lab_orders
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE IF NOT EXISTS referrals (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id           UUID REFERENCES patients (id) ON DELETE CASCADE,
    referring_doctor_id  TEXT REFERENCES doctors (id) ON DELETE SET NULL,
    target_provider_name TEXT,
    target_facility      TEXT,
    specialty            TEXT NOT NULL,
    reason               TEXT NOT NULL,
    urgency              TEXT NOT NULL DEFAULT 'routine'
                             CHECK (urgency IN ('routine', 'urgent', 'emergent')),
    status               TEXT NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending', 'sent', 'completed', 'cancelled')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at         TIMESTAMPTZ,
    deleted_at           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_referrals_patient
    ON referrals (patient_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_referrals_referring_doctor
    ON referrals (referring_doctor_id);

DROP TRIGGER IF EXISTS trg_referrals_updated_at ON referrals;
CREATE TRIGGER trg_referrals_updated_at BEFORE UPDATE ON referrals
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ===========================================================================
-- Documents and reports
-- ===========================================================================

CREATE TABLE IF NOT EXISTS reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID REFERENCES workflows (id) ON DELETE SET NULL,
    patient_id  UUID REFERENCES patients (id) ON DELETE CASCADE,
    call_log_id UUID REFERENCES call_logs (id) ON DELETE SET NULL,
    report_data JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reports_workflow ON reports (workflow_id);
CREATE INDEX IF NOT EXISTS idx_reports_patient  ON reports (patient_id);
CREATE INDEX IF NOT EXISTS idx_reports_call_log ON reports (call_log_id);


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
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pdf_documents_patient
    ON pdf_documents (patient_id) WHERE deleted_at IS NULL;


-- ===========================================================================
-- Audit trail
--
-- Append-only, and enforced as such by a trigger rather than by convention.
-- The backend connects with the service role key, which bypasses RLS but not
-- triggers — so this holds even for a bug in our own code.
--
-- doctor_id is the tenant the event belongs to; actor is who performed it.
-- They differ when a webhook or a scheduled job acts on a tenant's behalf.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id   TEXT REFERENCES doctors (id) ON DELETE SET NULL,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   UUID,
    patient_id  UUID,
    metadata    JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- patient_id is deliberately NOT a foreign key. An access event must outlive
-- the record it describes, including a hard deletion, or the trail has a hole
-- exactly where it matters most.

CREATE INDEX IF NOT EXISTS idx_audit_log_doctor
    ON audit_log (doctor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_patient
    ON audit_log (patient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity
    ON audit_log (entity_type, entity_id);

CREATE OR REPLACE FUNCTION audit_log_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_log_append_only ON audit_log;
CREATE TRIGGER trg_audit_log_append_only
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();

COMMIT;
