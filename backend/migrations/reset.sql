-- ===========================================================================
-- ⚠️  DESTRUCTIVE. Drops every Clarus table and everything in them.
--
-- Deliberately not numbered: this is not a migration and must never run as
-- part of a sequence. It exists for one situation — a development database
-- whose tables were built by hand in the dashboard and therefore lack the
-- referential actions, indexes and triggers that 000_initial_schema.sql
-- defines. CREATE TABLE IF NOT EXISTS cannot retrofit an ON DELETE clause, so
-- the honest fix on an empty database is to start again.
--
-- Do NOT run this against a database holding real data. There is no undo, and
-- for PHI there is no acceptable version of "we restored most of it".
--
-- Usage:
--     psql "$DATABASE_URL" -f migrations/reset.sql
--     psql "$DATABASE_URL" -f migrations/000_initial_schema.sql
-- ===========================================================================

BEGIN;

SET search_path = public, pg_temp;

-- CASCADE takes the foreign keys with each table, so drop order does not
-- matter. Listed roughly leaf-first anyway, so a failure is readable.
DROP TABLE IF EXISTS audit_log          CASCADE;
DROP TABLE IF EXISTS pdf_documents      CASCADE;
DROP TABLE IF EXISTS reports            CASCADE;
DROP TABLE IF EXISTS staff_assignments  CASCADE;
DROP TABLE IF EXISTS referrals          CASCADE;
DROP TABLE IF EXISTS lab_orders         CASCADE;
DROP TABLE IF EXISTS notifications      CASCADE;
DROP TABLE IF EXISTS patient_medications CASCADE;
DROP TABLE IF EXISTS patient_conditions CASCADE;
DROP TABLE IF EXISTS appointments       CASCADE;
DROP TABLE IF EXISTS call_logs          CASCADE;
DROP TABLE IF EXISTS workflows          CASCADE;
DROP TABLE IF EXISTS patients           CASCADE;
DROP TABLE IF EXISTS doctors            CASCADE;

-- The triggers went with their tables; the functions did not.
DROP FUNCTION IF EXISTS set_updated_at()       CASCADE;
DROP FUNCTION IF EXISTS audit_log_append_only() CASCADE;

COMMIT;
