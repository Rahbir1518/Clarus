-- ===========================================================================
-- Clarus — calls answered in the browser
--
-- Adds the one column CALL_TRANSPORT=web needs. On that transport a workflow's
-- call_patient node dials nothing: it parks the run, and the call is answered
-- later from the browser over WebRTC. The dynamic variables the agent speaks
-- are built when the run parks and stored here, so whoever answers is handed
-- exactly what the run built rather than a rebuild from a patient row that
-- may have changed in between.
--
-- Nullable, and NULL on every row that is not a browser call. Written by the
-- engine only (app/engine/nodes.py); no route writes call_logs from a request
-- body. RLS on call_logs keys on doctor_id, which is untouched, so the new
-- column is covered by the existing policies without restating them — the
-- same argument 002_call_outcomes.sql makes.
--
-- Apply after 002_call_outcomes.sql:
--     psql "$DATABASE_URL" -f migrations/003_browser_calls.sql
-- or paste it into the Supabase SQL editor.
-- ===========================================================================

BEGIN;

SET search_path = public, pg_temp;

ALTER TABLE call_logs
    ADD COLUMN IF NOT EXISTS call_variables JSONB;

COMMIT;
