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
--
-- This file is FORWARD-ONLY and NOT idempotent as a whole. The CREATE TABLE
-- and CREATE INDEX statements use IF NOT EXISTS, but the CREATE TABLE bodies
-- carry the column definitions, so re-running this against a database whose
-- tables already exist will silently skip every table and add nothing. It is
-- an initial schema, not a patch: run it once, on an empty database. To change
-- an existing database, add a numbered forward migration instead.
--
-- Nothing here backfills or rewrites data, because it only ever runs on an
-- empty database. If you are importing records from the old Supabase project,
-- see migrations/legacy_import_auth0_to_clerk.sql — that is where the tenant
-- key remapping and the doctors backfill live.
-- ===========================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Conventions
--
-- doctor_id is TEXT, not UUID. It holds the `sub` claim of a verified JWT and
-- is the tenant key for the entire database. The backend derives it from the
-- token signature chain — never from a request parameter, query string or body
-- field (see app/db/tenancy.py, and app/core/security.py for the verification).
--
-- The design is deliberately provider-agnostic: it needs a verified subject and
-- does not care who issued it. Under Clerk those values look like
-- 'user_2abc...'; under the previous Auth0 setup they looked like 'auth0|65f...'
-- or 'google-oauth2|1179...'. Only the format of the strings changes, never the
-- structure of the tenancy.
--
-- !! The backend on disk still verifies Auth0 tokens. app/core/config.py
-- !! requires AUTH0_DOMAIN / AUTH0_AUDIENCE and app/core/security.py pins the
-- !! Auth0 issuer and JWKS URL; the frontend uses @auth0/auth0-react. Nothing
-- !! in this schema depends on which of the two is live — but until that code
-- !! is switched, the subjects arriving here will be Auth0 subjects, and mixing
-- !! the two formats in one database means two tenants per human being.
--
-- Tenancy is per-DOCTOR, matching TENANT_TABLES in app/db/tenancy.py. If a
-- practice ever needs several clinicians to share one patient roster, that is
-- an organizations table above doctors and a different tenant key, and it
-- retargets every foreign key defined below. REBUILD_CHECKLIST.md phase 3 asks
-- for exactly that (org_id plus admin/physician/staff/read_only roles), so
-- treat the current model as a deliberate first step rather than the end state.
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
--
-- The tenant table, which the old schema never had: doctor_id was a bare string
-- on every table, referencing nothing. A typo in a token subject created a
-- silent new tenant, and there was nowhere to record a clinician's name, NPI or
-- practice.
--
-- id is the verified JWT subject, so this table is created first and everything
-- that carries a doctor_id points at it.
--
-- !! OPERATIONAL CONSEQUENCE OF THESE FOREIGN KEYS !!
-- A doctors row must exist BEFORE the first patient, workflow, call log or
-- appointment is written for that tenant, or the insert fails on the FK. The
-- authenticated request path is responsible for that: app/db/doctors.py upserts
-- the subject on first sight of it (INSERT ... ON CONFLICT (id) DO NOTHING via
-- postgrest's ignore_duplicates), called from get_tenant_scope in
-- app/api/deps.py so no route can forget. Do not remove that call.
CREATE TABLE IF NOT EXISTS doctors (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT,
    phone         TEXT,

    -- National Provider Identifier. Unique where present, but genuinely
    -- unknown for a doctor whose row was created from a token claim, so the
    -- uniqueness is enforced by a partial index rather than a column
    -- constraint (a UNIQUE column would collapse every NULL into one row in
    -- some engines and, more practically, invites a '' placeholder).
    npi           TEXT,

    specialty     TEXT,
    practice_name TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_doctors_npi
    ON doctors (npi) WHERE npi IS NOT NULL;

DROP TRIGGER IF EXISTS trg_doctors_updated_at ON doctors;
CREATE TRIGGER trg_doctors_updated_at BEFORE UPDATE ON doctors
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ===========================================================================
-- Core tenant-owned tables
--
-- Soft deletes: every table below that holds PHI carries deleted_at. Medical
-- record retention rules outlast a user clicking a delete button, and the child
-- tables are ON DELETE CASCADE, so one hard delete of a patient used to take
-- their conditions, medications, call transcripts, labs and referrals with it.
-- app/db/tenancy.py now writes deleted_at instead of issuing DELETE, and filters
-- deleted_at IS NULL on every read.
--
-- The CASCADE clauses are kept anyway. They are no longer the normal path, but
-- a genuine erasure request has to be executable by someone with direct
-- database access, and having the graph cascade correctly is what makes that
-- one statement instead of nine in the right order.
-- ===========================================================================

-- patients ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patients (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id         TEXT NOT NULL REFERENCES doctors (id),
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

    -- 'moderate', not 'medium'. The constraint used to read
    -- ('low','medium','high') while the only writer — the risk select in
    -- frontend/app/(app)/patients/[patientId]/page.tsx — offered 'moderate',
    -- so saving a moderate-risk patient failed the check on every attempt.
    -- One spelling, and it is the one the UI already sends.
    risk_level        TEXT NOT NULL DEFAULT 'low'
                          CHECK (risk_level IN ('low', 'moderate', 'high')),
    notes             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at        TIMESTAMPTZ
);

-- Partial on deleted_at because every application read filters it out, so the
-- index only needs to cover live rows.
CREATE INDEX IF NOT EXISTS idx_patients_doctor
    ON patients (doctor_id) WHERE deleted_at IS NULL;

-- An MRN is only unique within a practice, not globally. Soft-deleted rows are
-- excluded, otherwise a deleted patient would permanently reserve their MRN
-- against re-registration.
CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_doctor_mrn
    ON patients (doctor_id, mrn) WHERE mrn IS NOT NULL AND deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_patients_updated_at ON patients;
CREATE TRIGGER trg_patients_updated_at BEFORE UPDATE ON patients
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- workflows -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS workflows (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id   TEXT NOT NULL REFERENCES doctors (id),

    -- DEPRECATED in favour of doctors.name; do not add new readers.
    --
    -- Read as workflow.get("doctor_name") by the old engine to personalise what
    -- the voice agent says, but never created — so every AI call told patients
    -- "your doctor" instead of a name. Kept because the read path has not moved
    -- yet: the engine that consumed it is not in the tree today (it lives in
    -- git at 91382a9 and is being re-ported), and the appointments page reads a
    -- doctor_name out of call_logs.execution_log. Once the voice context is
    -- built from a join to doctors, a later migration drops this column.
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

-- No deleted_at: a workflow is automation configuration, not a medical record.
-- Deleting one is allowed to be a delete.
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
    doctor_id       TEXT NOT NULL REFERENCES doctors (id),

    workflow_id     UUID REFERENCES workflows (id) ON DELETE SET NULL,
    patient_id      UUID REFERENCES patients (id) ON DELETE CASCADE,
    trigger_node    TEXT,

    -- Left unconstrained on purpose. The re-ported engine writes 'running',
    -- 'completed' and 'failed'; the frontend also renders 'initiated'
    -- (frontend/app/(app)/calls/page.tsx) and the tests use 'pending' and
    -- 'done'. Pinning a CHECK here before the engine is back in the tree would
    -- constrain a vocabulary that is still moving.
    status          TEXT NOT NULL DEFAULT 'pending',

    outcome         TEXT,
    keypress        TEXT,
    conversation_id TEXT,
    transcript      TEXT,
    execution_log   JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- A transcript is PHI, so this is soft-deleted like the rest.
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_call_logs_doctor
    ON call_logs (doctor_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_call_logs_workflow ON call_logs (workflow_id);
CREATE INDEX IF NOT EXISTS idx_call_logs_patient  ON call_logs (patient_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_call_logs_conversation
    ON call_logs (conversation_id)
    WHERE conversation_id IS NOT NULL AND deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_call_logs_updated_at ON call_logs;
CREATE TRIGGER trg_call_logs_updated_at BEFORE UPDATE ON call_logs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- appointments --------------------------------------------------------------
--
-- The gap this closes: the codebase creates Google Calendar events, stores
-- patient email addresses to invite them, and ships an /appointments page — but
-- nothing modelled an appointment. That page currently reconstructs them by
-- listing call logs and scanning execution_log JSON for schedule_appointment
-- steps, pulling the calendar event id out of a JSON blob
-- (frontend/app/(app)/appointments/page.tsx). A call is not an appointment: it
-- is the conversation that produced one, and appointments booked any other way
-- were invisible.
--
-- This table is empty until the calendar path is re-ported to write it. That
-- work is what retires the JSON scanning.
CREATE TABLE IF NOT EXISTS appointments (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id         TEXT NOT NULL REFERENCES doctors (id),
    patient_id        UUID NOT NULL REFERENCES patients (id) ON DELETE CASCADE,
    workflow_id       UUID REFERENCES workflows (id) ON DELETE SET NULL,

    -- The call that booked it, where there was one. Appointments also arrive
    -- without a call, hence nullable.
    call_log_id       UUID REFERENCES call_logs (id) ON DELETE SET NULL,

    -- Google Calendar event id. The row is the record; Google is the delivery
    -- mechanism, and the two go out of sync the first time an API call fails.
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
    deleted_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_appointments_doctor
    ON appointments (doctor_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_appointments_patient  ON appointments (patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_starts   ON appointments (starts_at);

-- One row per calendar event, so a retried booking cannot double-book.
CREATE UNIQUE INDEX IF NOT EXISTS idx_appointments_calendar_event
    ON appointments (calendar_event_id)
    WHERE calendar_event_id IS NOT NULL AND deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_appointments_updated_at ON appointments;
CREATE TRIGGER trg_appointments_updated_at BEFORE UPDATE ON appointments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ===========================================================================
-- Patient-owned child tables
--
-- These carry no doctor_id. Ownership resolves through patient_id, and the
-- backend verifies the parent patient belongs to the caller before touching
-- them (see app/db/tenancy.py).
--
-- The CHECK vocabularies below were taken from what the application actually
-- writes, not from what reads well. Where a column's values come from
-- unvalidated workflow node parameters, it is left as free text and says so.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS patient_conditions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id   UUID NOT NULL REFERENCES patients (id) ON DELETE CASCADE,
    icd10_code   TEXT NOT NULL,
    description  TEXT NOT NULL,
    hcc_category TEXT,
    raf_impact   NUMERIC(6, 3),

    -- The default used to be 'active', a value nothing writes and nothing
    -- renders. The condition select offers exactly these three
    -- (frontend/app/(app)/patients/[patientId]/page.tsx:523-525) and the
    -- dashboard has a display config keyed by the same three
    -- (frontend/app/(app)/dashboard/page.tsx:200-202), with 'documented' as
    -- the fallback on read. Default matches the UI's default now.
    status       TEXT NOT NULL DEFAULT 'documented'
                     CHECK (status IN ('documented', 'review_needed',
                                       'pending_review')),
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

    -- Free text, for the outside prescriber whose name arrived on a fax or was
    -- read out of an uploaded PDF. Not a tenant, not resolvable, still needs
    -- recording.
    prescriber           TEXT,

    -- The prescriber when it was one of our own doctors. Distinct from the
    -- column above rather than replacing it, because most prescribers on an
    -- intake list are not users of this system.
    --
    -- Must be set from the verified token, never from a request body: the
    -- referrals/medications write path goes through insert_for_patient, whose
    -- sanitiser only strips a field literally named doctor_id.
    prescriber_doctor_id TEXT REFERENCES doctors (id),

    start_date           DATE,
    end_date             DATE,

    -- 'on_hold' is in the medication select
    -- (frontend/app/(app)/patients/[patientId]/page.tsx:642) and rendered as
    -- "On Hold" at :695. 'completed' reads like the obvious third value and is
    -- written by nothing.
    status               TEXT NOT NULL DEFAULT 'active'
                             CHECK (status IN ('active', 'discontinued', 'on_hold')),
    notes                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_patient_medications_patient
    ON patient_medications (patient_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_patient_medications_prescriber_doctor
    ON patient_medications (prescriber_doctor_id);

DROP TRIGGER IF EXISTS trg_patient_medications_updated_at ON patient_medications;
CREATE TRIGGER trg_patient_medications_updated_at BEFORE UPDATE ON patient_medications
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ===========================================================================
-- Secondary tables (carried forward from the old 001_create_new_tables.sql,
-- which is the only schema artefact that survived)
--
-- All four of these change state after insert — a notification is read, a lab
-- is collected, a referral is sent — so they get updated_at and the shared
-- trigger like the core tables. Previously they had only created_at and a
-- single completion timestamp, which recorded the end of a lifecycle but not
-- any step within it.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS notifications (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID REFERENCES patients (id) ON DELETE CASCADE,
    recipient  TEXT NOT NULL,
    message    TEXT NOT NULL,

    -- Deliberately unconstrained. The engine writes
    -- params.get("priority", "normal") straight from a workflow node, and a
    -- workflow authored through the API rather than the builder can carry any
    -- string at all. The builder's select offers normal/urgent/routine/stat
    -- (frontend/components/workflow/PropertiesPanel.tsx:22-27), which is not
    -- the same as a guarantee. A CHECK here would turn a cosmetic data-quality
    -- problem into a failed insert in the middle of a patient call — validate
    -- node parameters in the engine first, then constrain this column.
    priority   TEXT NOT NULL DEFAULT 'normal',

    status     TEXT NOT NULL DEFAULT 'unread'
                   CHECK (status IN ('unread', 'read')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at    TIMESTAMPTZ
);

DROP TRIGGER IF EXISTS trg_notifications_updated_at ON notifications;
CREATE TRIGGER trg_notifications_updated_at BEFORE UPDATE ON notifications
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE IF NOT EXISTS lab_orders (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id   UUID REFERENCES patients (id) ON DELETE CASCADE,
    test_type    TEXT NOT NULL,

    -- Unconstrained for the same reason as notifications.priority: the value
    -- is a workflow node parameter the engine does not validate.
    priority     TEXT NOT NULL DEFAULT 'routine',

    -- Only 'pending' is written today; the rest are the lifecycle the status is
    -- for. A CHECK that lists states nothing has reached yet is still worth
    -- having — it is the misspelling of 'cancelled' that it catches.
    status       TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'collected', 'completed',
                                       'cancelled')),
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    deleted_at   TIMESTAMPTZ
);

DROP TRIGGER IF EXISTS trg_lab_orders_updated_at ON lab_orders;
CREATE TRIGGER trg_lab_orders_updated_at BEFORE UPDATE ON lab_orders
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE IF NOT EXISTS referrals (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id           UUID REFERENCES patients (id) ON DELETE CASCADE,

    -- Who made the referral. A referral with no referrer is unanswerable at
    -- audit time, and this table previously had no doctor on it in any form.
    -- Same warning as patient_medications.prescriber_doctor_id: derive it from
    -- the token, because the child-table write path does not strip it.
    referring_doctor_id  TEXT REFERENCES doctors (id),

    -- Where it went. No foreign key, by design: the destination is a
    -- specialist or clinic outside this system in the overwhelming majority of
    -- cases, and forcing them into doctors would mean inventing tenant rows for
    -- people who never log in.
    target_provider_name TEXT,
    target_facility      TEXT,

    specialty            TEXT NOT NULL,
    reason               TEXT NOT NULL,

    -- 'emergent', not 'stat' — the urgency select offers
    -- routine/urgent/emergent (PropertiesPanel.tsx:29-33) while 'stat' belongs
    -- to the separate priority vocabulary. Constrained despite also coming from
    -- a node parameter, because unlike priority the engine's fallback
    -- ('routine') is inside the list; a bad value here fails loudly at the one
    -- place that can still be fixed by editing the workflow.
    urgency              TEXT NOT NULL DEFAULT 'routine'
                             CHECK (urgency IN ('routine', 'urgent', 'emergent')),
    status               TEXT NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending', 'sent', 'completed',
                                               'cancelled')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at         TIMESTAMPTZ,
    deleted_at           TIMESTAMPTZ
);

DROP TRIGGER IF EXISTS trg_referrals_updated_at ON referrals;
CREATE TRIGGER trg_referrals_updated_at BEFORE UPDATE ON referrals
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE IF NOT EXISTS staff_assignments (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id   UUID REFERENCES patients (id) ON DELETE CASCADE,
    staff_id     TEXT NOT NULL,
    task_type    TEXT NOT NULL,
    due_date     DATE,
    status       TEXT NOT NULL DEFAULT 'assigned'
                     CHECK (status IN ('assigned', 'in_progress', 'completed',
                                       'cancelled')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

DROP TRIGGER IF EXISTS trg_staff_assignments_updated_at ON staff_assignments;
CREATE TRIGGER trg_staff_assignments_updated_at BEFORE UPDATE ON staff_assignments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


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
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- raw_text is the full extracted text of a clinical document, so this is
    -- among the most PHI-dense tables here. Soft-deleted.
    deleted_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_notifications_patient      ON notifications (patient_id);
CREATE INDEX IF NOT EXISTS idx_lab_orders_patient         ON lab_orders (patient_id)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_referrals_patient          ON referrals (patient_id)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_referrals_referring_doctor ON referrals (referring_doctor_id);
CREATE INDEX IF NOT EXISTS idx_staff_assignments_patient  ON staff_assignments (patient_id);
CREATE INDEX IF NOT EXISTS idx_staff_assignments_staff    ON staff_assignments (staff_id);
CREATE INDEX IF NOT EXISTS idx_reports_workflow           ON reports (workflow_id);
CREATE INDEX IF NOT EXISTS idx_reports_patient            ON reports (patient_id);
CREATE INDEX IF NOT EXISTS idx_pdf_documents_patient      ON pdf_documents (patient_id)
    WHERE deleted_at IS NULL;


-- ===========================================================================
-- audit_log
--
-- Who looked at whose chart. There is an /audit-log page in the frontend, and
-- what it shows today is a client-side projection of call_logs.execution_log —
-- a record of what the automation did, which is not the same thing as a record
-- of who read a patient record. PHI access needs the second one.
--
-- Append-only in practice. That is not enforced here, because the backend holds
-- the service role key and would bypass any rule that tried: a role with UPDATE
-- revoked is only meaningful once something connects as a role that is not the
-- service role. Enforce it in the write path, and treat the absence of a DELETE
-- anywhere in the codebase as the current guarantee.
--
-- Empty until the application writes to it. A table like this is worse than
-- nothing if its emptiness is mistaken for "no one accessed anything".
-- ===========================================================================

CREATE TABLE IF NOT EXISTS audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Nullable: a webhook from ElevenLabs or a scheduled job acts on a tenant's
    -- data without a tenant of its own, and dropping those events would leave
    -- exactly the gaps an audit trail exists to close.
    doctor_id   TEXT REFERENCES doctors (id),

    actor       TEXT NOT NULL,              -- subject or service that acted
    action      TEXT NOT NULL,              -- read | create | update | delete
    entity_type TEXT NOT NULL,              -- 'patient', 'call_log', ...

    -- UUID, so this addresses the entity tables but not doctors (whose key is
    -- text). Doctor-level events are described by actor and doctor_id instead.
    entity_id   UUID,

    -- Denormalised so "everything touching this patient" is one index scan
    -- rather than a union over every entity type. No foreign key: the audit
    -- trail has to outlive the record it describes, including a hard erasure.
    patient_id  UUID,

    metadata    JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_doctor  ON audit_log (doctor_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_patient ON audit_log (patient_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log (created_at);


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

ALTER TABLE doctors             ENABLE ROW LEVEL SECURITY;
ALTER TABLE patients            ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflows           ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_logs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments        ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_conditions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_medications ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications       ENABLE ROW LEVEL SECURITY;
ALTER TABLE lab_orders          ENABLE ROW LEVEL SECURITY;
ALTER TABLE referrals           ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_assignments   ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports             ENABLE ROW LEVEL SECURITY;
ALTER TABLE pdf_documents       ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log           ENABLE ROW LEVEL SECURITY;

-- No permissive policies are defined. With RLS enabled and zero policies,
-- every non-superuser, non-bypassing role is denied. Add scoped policies here
-- if and when a non-service-role client is introduced.

COMMIT;
