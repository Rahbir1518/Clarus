-- ===========================================================================
-- Clarus — practice opening hours and appointment length
--
-- Set by the doctor in the app (Settings -> Clinic hours) and kept until they
-- change them. The agent reads both during a call to offer free times and to
-- check a time the patient proposes; the booking step reads them again after
-- the call. See app/scheduling/availability.py.
--
-- clinic_hours is {"mon": [{"start": "09:00", "end": "17:00"}], ...}, wall-clock
-- times in the deployment's DEFAULT_TIMEZONE. NULL until first saved, and NULL
-- means "not set" rather than "closed": the agent then offers no times at all.
-- The shape is validated by app/schemas/practice.py on every write.
--
-- On `doctors` because hours belong to the practice, and doctors is the tenant
-- root. RLS on doctors keys on id, which is untouched.
--
-- Apply after 003_browser_calls.sql:
--     psql "$DATABASE_URL" -f migrations/004_practice_hours.sql
-- ===========================================================================

BEGIN;

SET search_path = public, pg_temp;

ALTER TABLE doctors
    ADD COLUMN IF NOT EXISTS clinic_hours JSONB,
    ADD COLUMN IF NOT EXISTS appointment_minutes INTEGER
        CHECK (appointment_minutes IS NULL OR appointment_minutes BETWEEN 5 AND 240);

COMMIT;
