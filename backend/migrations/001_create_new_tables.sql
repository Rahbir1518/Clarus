-- =========================================================================
-- MedTrigger — Database schema extensions
-- Run this in the Supabase SQL Editor (Dashboard → SQL → New Query)
-- =========================================================================

-- 1. Notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id  UUID REFERENCES patients(id) ON DELETE CASCADE,
    recipient   TEXT NOT NULL,
    message     TEXT NOT NULL,
    priority    TEXT NOT NULL DEFAULT 'normal',
    status      TEXT NOT NULL DEFAULT 'unread',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at     TIMESTAMPTZ
);

-- 2. Lab orders table
CREATE TABLE IF NOT EXISTS lab_orders (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id   UUID REFERENCES patients(id) ON DELETE CASCADE,
    test_type    TEXT NOT NULL,
    priority     TEXT NOT NULL DEFAULT 'routine',
    status       TEXT NOT NULL DEFAULT 'pending',
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- 3. Referrals table
CREATE TABLE IF NOT EXISTS referrals (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id   UUID REFERENCES patients(id) ON DELETE CASCADE,
    specialty    TEXT NOT NULL,
    reason       TEXT NOT NULL,
    urgency      TEXT NOT NULL DEFAULT 'routine',
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- 4. Staff assignments table
CREATE TABLE IF NOT EXISTS staff_assignments (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id   UUID REFERENCES patients(id) ON DELETE CASCADE,
    staff_id     TEXT NOT NULL,
    task_type    TEXT NOT NULL,
    due_date     DATE,
    status       TEXT NOT NULL DEFAULT 'assigned',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- 5. Reports table
CREATE TABLE IF NOT EXISTS reports (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    workflow_id  UUID REFERENCES workflows(id) ON DELETE SET NULL,
    patient_id   UUID REFERENCES patients(id) ON DELETE CASCADE,
    call_log_id  UUID REFERENCES call_logs(id) ON DELETE SET NULL,
    report_data  JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 6. PDF documents table (stores metadata + extracted data from uploaded PDFs)
CREATE TABLE IF NOT EXISTS pdf_documents (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id    UUID REFERENCES patients(id) ON DELETE CASCADE,
    filename      TEXT NOT NULL,
    file_url      TEXT,
    page_count    INTEGER,
    raw_text      TEXT,
    patient_info  JSONB DEFAULT '{}'::JSONB,
    lab_results   JSONB DEFAULT '[]'::JSONB,
    tables_data   JSONB DEFAULT '[]'::JSONB,
    uploaded_by   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_notifications_patient    ON notifications(patient_id);
CREATE INDEX IF NOT EXISTS idx_lab_orders_patient       ON lab_orders(patient_id);
CREATE INDEX IF NOT EXISTS idx_referrals_patient        ON referrals(patient_id);
CREATE INDEX IF NOT EXISTS idx_staff_assignments_patient ON staff_assignments(patient_id);
CREATE INDEX IF NOT EXISTS idx_staff_assignments_staff   ON staff_assignments(staff_id);
CREATE INDEX IF NOT EXISTS idx_reports_workflow          ON reports(workflow_id);
CREATE INDEX IF NOT EXISTS idx_reports_patient           ON reports(patient_id);
CREATE INDEX IF NOT EXISTS idx_pdf_documents_patient     ON pdf_documents(patient_id);
