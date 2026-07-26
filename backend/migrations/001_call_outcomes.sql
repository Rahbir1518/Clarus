-- ===========================================================================
-- Clarus — call outcome columns
--
-- Adds the structured result of an ElevenLabs call to call_logs, so the
-- outcome is stored as typed data rather than re-derived from the transcript
-- on every read. The old system kept only a free-text outcome and re-ran a
-- regex over the transcript whenever it needed to know whether the patient had
-- agreed, which is how it ended up booking appointments off the word "yes"
-- appearing in the agent's own dialogue.
-- ===========================================================================

BEGIN;

ALTER TABLE call_logs
    -- Everything the agent extracted, exactly as received. Kept verbatim so a
    -- parsing change can be replayed against historical calls without another
    -- round of phoning patients.
    ADD COLUMN IF NOT EXISTS data_collection JSONB NOT NULL DEFAULT '{}'::JSONB,

    -- Nullable on purpose, and it must stay that way. NULL means "the call did
    -- not establish this", which is a genuinely different state from false.
    -- Collapsing the two is what makes a voicemail look like a refusal.
    ADD COLUMN IF NOT EXISTS patient_confirmed BOOLEAN,
    ADD COLUMN IF NOT EXISTS reached_patient   BOOLEAN,

    ADD COLUMN IF NOT EXISTS confirmed_date TEXT,
    ADD COLUMN IF NOT EXISTS confirmed_time TEXT,

    -- IANA name, e.g. 'America/Toronto'. Carried per row rather than assumed:
    -- the old code resolved dates in America/Toronto and then created calendar
    -- events in America/New_York, which agreed by luck until it wouldn't.
    ADD COLUMN IF NOT EXISTS timezone TEXT,

    ADD COLUMN IF NOT EXISTS availability_notes TEXT,
    ADD COLUMN IF NOT EXISTS callback_requested BOOLEAN,

    -- Set whenever the result is not safe to act on unattended. Defaults to
    -- true so a row that no webhook ever completed sits in the review queue
    -- instead of quietly looking finished.
    ADD COLUMN IF NOT EXISTS needs_review BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS reviewed_at  TIMESTAMPTZ,

    ADD COLUMN IF NOT EXISTS webhook_received_at TIMESTAMPTZ;

-- The review queue is the main operational read.
CREATE INDEX IF NOT EXISTS idx_call_logs_needs_review
    ON call_logs (doctor_id, created_at DESC) WHERE needs_review;

COMMIT;
