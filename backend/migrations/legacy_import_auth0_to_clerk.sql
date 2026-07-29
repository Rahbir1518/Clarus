-- ===========================================================================
-- Clarus — legacy upgrade: pre-doctors schema, Auth0 subjects → Clerk user IDs
--
-- THIS IS NOT PART OF THE NUMBERED MIGRATION SEQUENCE. Do not run it after
-- 000_initial_schema.sql on a fresh database — 000 already produces the end
-- state this script works towards, and every statement here would either fail
-- or do nothing.
--
-- Run this only against a database that has the OLD schema and real rows in it:
-- the eleven tables from the original 000, with doctor_id as a bare TEXT column
-- referencing nothing, no doctors table, and Auth0 subjects ('auth0|65f...',
-- 'google-oauth2|1179...') as tenant keys.
--
-- What it does, in one transaction:
--   1. rewrites every doctor_id from its Auth0 subject to the Clerk user ID
--   2. creates and backfills doctors, so the foreign keys have parents
--   3. adds the foreign keys
--   4. adds the new referral / medication / appointment / audit columns
--   5. cleans data that would fail the new CHECK constraints, then adds them
--   6. adds deleted_at and the soft-delete-aware indexes
--
-- Order matters and is not negotiable: remap before backfill (or doctors gets
-- rows for dead subjects), backfill before the foreign keys (or ADD CONSTRAINT
-- fails on the first orphan), clean before CHECK (or ADD CONSTRAINT fails on
-- the first bad value).
--
-- Take a snapshot first. This rewrites the tenant key of every row in the
-- database, and a partially-understood id_map is not something you want to
-- discover afterwards.
--
--   psql "$DATABASE_URL" -f migrations/legacy_import_auth0_to_clerk.sql
--
-- Forward-only and NOT idempotent. Re-running it fails loudly: the ADD
-- CONSTRAINT statements are not guarded, so the second run aborts on the first
-- duplicate constraint name and rolls back. That is the intended behaviour —
-- a script that rewrites tenant keys should not be quietly re-runnable.
-- ===========================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 0. The mapping
--
-- Clerk issues brand-new 'user_...' IDs unless the users were imported with
-- their external IDs preserved. Nothing here can tell the difference between a
-- subject that was never migrated and one whose mapping you forgot to include,
-- so it refuses to guess: fill this table from the Clerk export before running.
--
-- If Clerk DID preserve the external IDs and the subjects are unchanged, leave
-- the table empty. The remap in step 1 becomes a no-op and the guard passes,
-- because every doctor_id already matches Clerk's format.
-- ---------------------------------------------------------------------------

CREATE TEMP TABLE id_map (
    old_auth0_id TEXT PRIMARY KEY,
    new_clerk_id TEXT NOT NULL
) ON COMMIT DROP;

-- >>> EDIT THIS BLOCK. One row per user, from your Clerk export. <<<
INSERT INTO id_map (old_auth0_id, new_clerk_id) VALUES
    -- ('auth0|65f0a1b2c3d4e5f6a7b8c9d0',   'user_2abcdefghijklmnopqrstuvwxyz'),
    -- ('google-oauth2|117901234567890123', 'user_2zyxwvutsrqponmlkjihgfedcba')
    ('__placeholder__', '__placeholder__');
DELETE FROM id_map WHERE old_auth0_id = '__placeholder__';


-- Refuse to proceed if any live tenant key is neither mapped nor already a
-- Clerk ID. Without this the remap silently leaves those rows on their old
-- subject, they get their own doctors row in step 2, and the patients under them
-- become invisible the moment their owner logs in under a new ID — an orphaned
-- tenant that looks like data loss and is very hard to reconstruct later.
DO $$
DECLARE
    unmapped TEXT;
BEGIN
    SELECT string_agg(DISTINCT s.doctor_id, ', ')
      INTO unmapped
      FROM (
          SELECT doctor_id FROM patients
          UNION SELECT doctor_id FROM workflows
          UNION SELECT doctor_id FROM call_logs
      ) s
     WHERE s.doctor_id IS NOT NULL
       AND s.doctor_id NOT LIKE 'user\_%'
       AND NOT EXISTS (SELECT 1 FROM id_map m WHERE m.old_auth0_id = s.doctor_id);

    IF unmapped IS NOT NULL THEN
        RAISE EXCEPTION
            'Unmapped tenant keys, refusing to continue: %. Add them to id_map, '
            'or confirm they are already Clerk user IDs.', unmapped;
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- 1. Rewrite the tenant key everywhere it is stored
--
-- Only three tables carry doctor_id. The patient-owned child tables resolve
-- ownership through patient_id and need no rewriting, which is the one place
-- the denormalisation-averse design pays off.
-- ---------------------------------------------------------------------------

UPDATE patients  p SET doctor_id = m.new_clerk_id
    FROM id_map m WHERE p.doctor_id = m.old_auth0_id;
UPDATE workflows w SET doctor_id = m.new_clerk_id
    FROM id_map m WHERE w.doctor_id = m.old_auth0_id;
UPDATE call_logs c SET doctor_id = m.new_clerk_id
    FROM id_map m WHERE c.doctor_id = m.old_auth0_id;


-- ---------------------------------------------------------------------------
-- 2. The doctors table, created and backfilled before anything references it
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS doctors (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT,
    phone         TEXT,
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

ALTER TABLE doctors ENABLE ROW LEVEL SECURITY;

-- Every distinct tenant key that exists, with a placeholder name. 'Unknown' is
-- a marker the next statement looks for, not a display value.
INSERT INTO doctors (id, name)
SELECT DISTINCT s.doctor_id, 'Unknown'
FROM (
    SELECT doctor_id FROM patients
    UNION SELECT doctor_id FROM workflows
    UNION SELECT doctor_id FROM call_logs
) s
WHERE s.doctor_id IS NOT NULL
ON CONFLICT (id) DO NOTHING;

-- Improve the placeholders from the one place a real name was ever recorded.
-- Guarded on name = 'Unknown' so re-running cannot overwrite a name someone has
-- since corrected by hand.
UPDATE doctors d
SET name = w.doctor_name
FROM workflows w
WHERE w.doctor_id = d.id
  AND w.doctor_name IS NOT NULL
  AND d.name = 'Unknown';


-- ---------------------------------------------------------------------------
-- 3. Foreign keys. Safe now, and only now.
-- ---------------------------------------------------------------------------

ALTER TABLE patients  ADD CONSTRAINT fk_patients_doctor
    FOREIGN KEY (doctor_id) REFERENCES doctors (id);
ALTER TABLE workflows ADD CONSTRAINT fk_workflows_doctor
    FOREIGN KEY (doctor_id) REFERENCES doctors (id);
ALTER TABLE call_logs ADD CONSTRAINT fk_call_logs_doctor
    FOREIGN KEY (doctor_id) REFERENCES doctors (id);


-- ---------------------------------------------------------------------------
-- 4. New columns on referrals and medications
--
-- workflows.doctor_name is NOT dropped here. It is the source the backfill
-- above just read, and the read path has not moved to doctors.name yet. It is
-- deprecated; dropping it is a later migration.
-- ---------------------------------------------------------------------------

ALTER TABLE referrals
    ADD COLUMN referring_doctor_id  TEXT REFERENCES doctors (id),
    ADD COLUMN target_provider_name TEXT,
    ADD COLUMN target_facility      TEXT;

CREATE INDEX IF NOT EXISTS idx_referrals_referring_doctor
    ON referrals (referring_doctor_id);

-- patient_medications.patient_id → patients(id) already exists. Only the
-- prescriber link is missing. The free-text `prescriber` column stays, for
-- outside prescribers who are not users of this system.
ALTER TABLE patient_medications
    ADD COLUMN prescriber_doctor_id TEXT REFERENCES doctors (id);

CREATE INDEX IF NOT EXISTS idx_patient_medications_prescriber_doctor
    ON patient_medications (prescriber_doctor_id);


-- ---------------------------------------------------------------------------
-- 5. CHECK constraints, after cleaning the data that would fail them
--
-- The vocabularies come from what the application writes, which is not what the
-- old defaults said. Anything outside the expected set aborts the transaction
-- rather than being coerced: a status this script has never heard of means
-- someone is writing a value nobody documented, and silently rewriting it to
-- the default would destroy that information.
-- ---------------------------------------------------------------------------

-- patients.risk_level: the old constraint allowed 'medium', which no writer
-- produced; the UI has always sent 'moderate', so every moderate-risk save
-- failed the check. One spelling, and it is the UI's.
ALTER TABLE patients DROP CONSTRAINT IF EXISTS patients_risk_level_check;
UPDATE patients SET risk_level = 'moderate' WHERE risk_level = 'medium';
UPDATE patients SET risk_level = 'low' WHERE risk_level IS NULL;

-- patient_conditions.status: the old default was 'active', a value the UI
-- neither writes nor renders — it falls back to 'documented' on read, so those
-- rows already displayed as documented. Make the stored value match.
UPDATE patient_conditions SET status = 'documented'
    WHERE status IS NULL OR status = 'active';

DO $$
DECLARE
    bad TEXT;
BEGIN
    SELECT string_agg(DISTINCT quote_literal(v.value), ', ') INTO bad FROM (
        SELECT 'patients.risk_level: '           || risk_level AS value FROM patients
          WHERE risk_level NOT IN ('low','moderate','high')
        UNION
        SELECT 'patient_conditions.status: '     || status FROM patient_conditions
          WHERE status NOT IN ('documented','review_needed','pending_review')
        UNION
        SELECT 'patient_medications.status: '    || status FROM patient_medications
          WHERE status NOT IN ('active','discontinued','on_hold')
        UNION
        SELECT 'notifications.status: '          || status FROM notifications
          WHERE status NOT IN ('unread','read')
        UNION
        SELECT 'lab_orders.status: '             || status FROM lab_orders
          WHERE status NOT IN ('pending','collected','completed','cancelled')
        UNION
        SELECT 'referrals.status: '              || status FROM referrals
          WHERE status NOT IN ('pending','sent','completed','cancelled')
        UNION
        SELECT 'referrals.urgency: '             || urgency FROM referrals
          WHERE urgency NOT IN ('routine','urgent','emergent')
        UNION
        SELECT 'staff_assignments.status: '      || status FROM staff_assignments
          WHERE status NOT IN ('assigned','in_progress','completed','cancelled')
    ) v;

    IF bad IS NOT NULL THEN
        RAISE EXCEPTION
            'Values outside the intended CHECK vocabularies: %. Decide what each '
            'one should become and clean it explicitly above, or widen the '
            'constraint — do not let this script guess.', bad;
    END IF;
END $$;

ALTER TABLE patients
    ADD CONSTRAINT patients_risk_level_check
    CHECK (risk_level IN ('low', 'moderate', 'high'));

ALTER TABLE patient_conditions
    ALTER COLUMN status SET DEFAULT 'documented',
    ADD CONSTRAINT patient_conditions_status_check
    CHECK (status IN ('documented', 'review_needed', 'pending_review'));

ALTER TABLE patient_medications
    ADD CONSTRAINT patient_medications_status_check
    CHECK (status IN ('active', 'discontinued', 'on_hold'));

ALTER TABLE notifications
    ADD CONSTRAINT notifications_status_check
    CHECK (status IN ('unread', 'read'));

ALTER TABLE lab_orders
    ADD CONSTRAINT lab_orders_status_check
    CHECK (status IN ('pending', 'collected', 'completed', 'cancelled'));

ALTER TABLE referrals
    ADD CONSTRAINT referrals_status_check
    CHECK (status IN ('pending', 'sent', 'completed', 'cancelled')),
    ADD CONSTRAINT referrals_urgency_check
    CHECK (urgency IN ('routine', 'urgent', 'emergent'));

ALTER TABLE staff_assignments
    ADD CONSTRAINT staff_assignments_status_check
    CHECK (status IN ('assigned', 'in_progress', 'completed', 'cancelled'));

-- notifications.priority and lab_orders.priority are deliberately left
-- unconstrained. Both are written straight from unvalidated workflow node
-- parameters (params.get("priority", ...)), so a CHECK converts a cosmetic data
-- problem into a failed insert during a patient call. Validate node parameters
-- in the engine, then constrain these in a follow-up migration.
--
-- call_logs.status is left unconstrained too: the engine writes running /
-- completed / failed, the UI renders 'initiated', and the tests use 'pending'
-- and 'done'. Settle the vocabulary before pinning it.


-- ---------------------------------------------------------------------------
-- 6. appointments and audit_log
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS appointments (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id         TEXT NOT NULL REFERENCES doctors (id),
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
    deleted_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_appointments_doctor
    ON appointments (doctor_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments (patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_starts  ON appointments (starts_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_appointments_calendar_event
    ON appointments (calendar_event_id)
    WHERE calendar_event_id IS NOT NULL AND deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_appointments_updated_at ON appointments;
CREATE TRIGGER trg_appointments_updated_at BEFORE UPDATE ON appointments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;


CREATE TABLE IF NOT EXISTS audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id   TEXT REFERENCES doctors (id),
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   UUID,
    patient_id  UUID,
    metadata    JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_doctor  ON audit_log (doctor_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_patient ON audit_log (patient_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log (created_at);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;


-- ---------------------------------------------------------------------------
-- 7. updated_at on the secondary tables that change state after insert
--
-- Backfilled from created_at rather than now(), so an untouched row does not
-- claim to have been modified at migration time.
-- ---------------------------------------------------------------------------

ALTER TABLE notifications
    ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE lab_orders
    ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE referrals
    ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE staff_assignments
    ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

UPDATE notifications      SET updated_at = created_at;
UPDATE lab_orders         SET updated_at = created_at;
UPDATE referrals          SET updated_at = created_at;
UPDATE staff_assignments  SET updated_at = created_at;

DROP TRIGGER IF EXISTS trg_notifications_updated_at ON notifications;
CREATE TRIGGER trg_notifications_updated_at BEFORE UPDATE ON notifications
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_lab_orders_updated_at ON lab_orders;
CREATE TRIGGER trg_lab_orders_updated_at BEFORE UPDATE ON lab_orders
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_referrals_updated_at ON referrals;
CREATE TRIGGER trg_referrals_updated_at BEFORE UPDATE ON referrals
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_staff_assignments_updated_at ON staff_assignments;
CREATE TRIGGER trg_staff_assignments_updated_at BEFORE UPDATE ON staff_assignments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ---------------------------------------------------------------------------
-- 8. Soft delete
--
-- Adding the column is the easy half. The other half is in the application:
-- app/db/tenancy.py must write deleted_at instead of issuing DELETE, and filter
-- deleted_at IS NULL on every read. A database with these columns and an
-- application that still hard-deletes is strictly worse than neither, because
-- it looks like retention is handled.
-- ---------------------------------------------------------------------------

ALTER TABLE patients            ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE call_logs           ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE patient_conditions  ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE patient_medications ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE lab_orders          ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE referrals           ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE pdf_documents       ADD COLUMN deleted_at TIMESTAMPTZ;

-- The unique indexes have to stop counting soft-deleted rows, or a deleted
-- patient permanently reserves their MRN against re-registration and a
-- soft-deleted call log blocks its conversation id from ever being reused.
DROP INDEX IF EXISTS idx_patients_doctor_mrn;
CREATE UNIQUE INDEX idx_patients_doctor_mrn
    ON patients (doctor_id, mrn) WHERE mrn IS NOT NULL AND deleted_at IS NULL;

DROP INDEX IF EXISTS idx_call_logs_conversation;
CREATE UNIQUE INDEX idx_call_logs_conversation
    ON call_logs (conversation_id)
    WHERE conversation_id IS NOT NULL AND deleted_at IS NULL;

-- The tenant/patient lookup indexes only need to cover live rows, since every
-- application read now filters deleted_at IS NULL.
DROP INDEX IF EXISTS idx_patients_doctor;
CREATE INDEX idx_patients_doctor ON patients (doctor_id) WHERE deleted_at IS NULL;

DROP INDEX IF EXISTS idx_call_logs_doctor;
CREATE INDEX idx_call_logs_doctor ON call_logs (doctor_id) WHERE deleted_at IS NULL;

DROP INDEX IF EXISTS idx_patient_conditions_patient;
CREATE INDEX idx_patient_conditions_patient
    ON patient_conditions (patient_id) WHERE deleted_at IS NULL;

DROP INDEX IF EXISTS idx_patient_medications_patient;
CREATE INDEX idx_patient_medications_patient
    ON patient_medications (patient_id) WHERE deleted_at IS NULL;

DROP INDEX IF EXISTS idx_lab_orders_patient;
CREATE INDEX idx_lab_orders_patient
    ON lab_orders (patient_id) WHERE deleted_at IS NULL;

DROP INDEX IF EXISTS idx_referrals_patient;
CREATE INDEX idx_referrals_patient
    ON referrals (patient_id) WHERE deleted_at IS NULL;

DROP INDEX IF EXISTS idx_pdf_documents_patient;
CREATE INDEX idx_pdf_documents_patient
    ON pdf_documents (patient_id) WHERE deleted_at IS NULL;

COMMIT;


-- ===========================================================================
-- Verification. Run after committing.
-- ===========================================================================

-- No orphaned tenants. Expect 0 rows.
SELECT doctor_id FROM patients  WHERE doctor_id NOT IN (SELECT id FROM doctors)
UNION SELECT doctor_id FROM workflows WHERE doctor_id NOT IN (SELECT id FROM doctors)
UNION SELECT doctor_id FROM call_logs WHERE doctor_id NOT IN (SELECT id FROM doctors);

-- No Auth0-shaped subjects left behind. Expect 0 rows.
SELECT DISTINCT doctor_id FROM (
    SELECT doctor_id FROM patients
    UNION SELECT doctor_id FROM workflows
    UNION SELECT doctor_id FROM call_logs
) s WHERE doctor_id LIKE '%|%';

-- Every distinct tenant key has a doctors row, and how many are still
-- placeholders (each needs a real name, from Clerk or from the clinician).
SELECT count(*) AS doctors, count(*) FILTER (WHERE name = 'Unknown') AS unnamed
FROM doctors;

-- RLS on the new tables. Expect relrowsecurity = true for all three.
SELECT relname, relrowsecurity FROM pg_class
WHERE relname IN ('doctors', 'appointments', 'audit_log') ORDER BY relname;

-- Row counts, to compare against the snapshot taken before the run.
SELECT 'patients' AS t, count(*) FROM patients
UNION ALL SELECT 'workflows', count(*) FROM workflows
UNION ALL SELECT 'call_logs', count(*) FROM call_logs;
