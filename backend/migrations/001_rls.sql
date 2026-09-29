BEGIN;

SET search_path = public, pg_temp;

CREATE OR REPLACE FUNCTION current_doctor_id()
RETURNS TEXT
LANGUAGE SQL
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT NULLIF(
        current_setting('request.jwt.claims', true)::JSONB ->> 'sub',
        ''
    )
$$;

CREATE OR REPLACE FUNCTION owns_patient(p_patient_id UUID)
RETURNS BOOLEAN
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.patients p
        WHERE p.id = p_patient_id
          AND p.doctor_id = current_doctor_id()
          AND p.deleted_at IS NULL
    )
$$;

CREATE OR REPLACE FUNCTION owns_workflow(p_workflow_id UUID)
RETURNS BOOLEAN
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    -- No deleted_at on workflows: they are retired via status = 'ARCHIVED' so
    -- that the call logs and reports they produced keep a live reference.
    -- Ownership is therefore the only question here.
    SELECT EXISTS (
        SELECT 1 FROM public.workflows w
        WHERE w.id = p_workflow_id
          AND w.doctor_id = current_doctor_id()
    )
$$;

CREATE OR REPLACE FUNCTION owns_call_log(p_call_log_id UUID)
RETURNS BOOLEAN
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.call_logs c
        WHERE c.id = p_call_log_id
          AND c.doctor_id = current_doctor_id()
          AND c.deleted_at IS NULL
    )
$$;


-- ===========================================================================
-- Lock 1 — grants
-- ===========================================================================

-- Supabase grants these roles broad table access by default, and its default
-- privileges hand the same to every table created later. Both have to go, or
-- the next migration silently re-exposes whatever it creates.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON FUNCTIONS FROM anon, authenticated;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM anon;
GRANT USAGE ON SCHEMA public TO authenticated, service_role;


REVOKE ALL ON FUNCTION
    current_doctor_id(),
    owns_patient(UUID),
    owns_workflow(UUID),
    owns_call_log(UUID)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    current_doctor_id(),
    owns_patient(UUID),
    owns_workflow(UUID),
    owns_call_log(UUID)
TO authenticated;

ALTER TABLE doctors             ENABLE ROW LEVEL SECURITY;
ALTER TABLE patients            ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflows           ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_logs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments        ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_conditions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_medications ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications       ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_assignments   ENABLE ROW LEVEL SECURITY;
ALTER TABLE lab_orders          ENABLE ROW LEVEL SECURITY;
ALTER TABLE referrals           ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports             ENABLE ROW LEVEL SECURITY;
ALTER TABLE pdf_documents       ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log           ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS doctors_self_select ON doctors;
CREATE POLICY doctors_self_select ON doctors
    FOR SELECT TO authenticated
    USING (id = current_doctor_id());

DROP POLICY IF EXISTS doctors_self_update ON doctors;
CREATE POLICY doctors_self_update ON doctors
    FOR UPDATE TO authenticated
    USING (id = current_doctor_id())
    WITH CHECK (id = current_doctor_id());


DROP POLICY IF EXISTS patients_tenant_isolation ON patients;
CREATE POLICY patients_tenant_isolation ON patients
    FOR ALL TO authenticated
    USING (doctor_id = current_doctor_id())
    WITH CHECK (doctor_id = current_doctor_id());

DROP POLICY IF EXISTS workflows_tenant_isolation ON workflows;
CREATE POLICY workflows_tenant_isolation ON workflows
    FOR ALL TO authenticated
    USING (doctor_id = current_doctor_id())
    WITH CHECK (doctor_id = current_doctor_id());

DROP POLICY IF EXISTS call_logs_tenant_isolation ON call_logs;
CREATE POLICY call_logs_tenant_isolation ON call_logs
    FOR ALL TO authenticated
    USING (doctor_id = current_doctor_id())
    WITH CHECK (
        doctor_id = current_doctor_id()
        -- Both nullable in the schema, and null is legitimate: an inbound call
        -- is logged before it has been matched to a patient or a workflow.
        AND (patient_id  IS NULL OR owns_patient(patient_id))
        AND (workflow_id IS NULL OR owns_workflow(workflow_id))
    );

DROP POLICY IF EXISTS appointments_tenant_isolation ON appointments;
CREATE POLICY appointments_tenant_isolation ON appointments
    FOR ALL TO authenticated
    USING (doctor_id = current_doctor_id())
    WITH CHECK (
        doctor_id = current_doctor_id()
        -- patient_id is NOT NULL here, so this is unconditional: there is no
        -- such thing as an appointment for nobody.
        AND owns_patient(patient_id)
        AND (workflow_id IS NULL OR owns_workflow(workflow_id))
        AND (call_log_id IS NULL OR owns_call_log(call_log_id))
    );


DROP POLICY IF EXISTS patient_conditions_tenant_isolation ON patient_conditions;
CREATE POLICY patient_conditions_tenant_isolation ON patient_conditions
    FOR ALL TO authenticated
    USING (owns_patient(patient_id))
    WITH CHECK (owns_patient(patient_id));

DROP POLICY IF EXISTS patient_medications_tenant_isolation ON patient_medications;
CREATE POLICY patient_medications_tenant_isolation ON patient_medications
    FOR ALL TO authenticated
    USING (owns_patient(patient_id))
    WITH CHECK (
        owns_patient(patient_id)
        AND (prescriber_doctor_id IS NULL
             OR prescriber_doctor_id = current_doctor_id())
    );

DROP POLICY IF EXISTS notifications_tenant_isolation ON notifications;
CREATE POLICY notifications_tenant_isolation ON notifications
    FOR ALL TO authenticated
    USING (owns_patient(patient_id))
    WITH CHECK (owns_patient(patient_id));

DROP POLICY IF EXISTS staff_assignments_tenant_isolation ON staff_assignments;
CREATE POLICY staff_assignments_tenant_isolation ON staff_assignments
    FOR ALL TO authenticated
    USING (owns_patient(patient_id))
    WITH CHECK (owns_patient(patient_id));

DROP POLICY IF EXISTS lab_orders_tenant_isolation ON lab_orders;
CREATE POLICY lab_orders_tenant_isolation ON lab_orders
    FOR ALL TO authenticated
    USING (owns_patient(patient_id))
    WITH CHECK (owns_patient(patient_id));

DROP POLICY IF EXISTS referrals_tenant_isolation ON referrals;
CREATE POLICY referrals_tenant_isolation ON referrals
    FOR ALL TO authenticated
    USING (owns_patient(patient_id))
    WITH CHECK (
        owns_patient(patient_id)
        AND (referring_doctor_id IS NULL
             OR referring_doctor_id = current_doctor_id())
    );

-- reports has no doctor_id of its own, and three foreign keys that each need
-- to stay inside one tenant.
DROP POLICY IF EXISTS reports_tenant_isolation ON reports;
CREATE POLICY reports_tenant_isolation ON reports
    FOR ALL TO authenticated
    USING (owns_patient(patient_id))
    WITH CHECK (
        owns_patient(patient_id)
        AND (workflow_id IS NULL OR owns_workflow(workflow_id))
        AND (call_log_id IS NULL OR owns_call_log(call_log_id))
    );

DROP POLICY IF EXISTS pdf_documents_tenant_isolation ON pdf_documents;
CREATE POLICY pdf_documents_tenant_isolation ON pdf_documents
    FOR ALL TO authenticated
    USING (owns_patient(patient_id))
    WITH CHECK (owns_patient(patient_id));


DROP POLICY IF EXISTS audit_log_tenant_read ON audit_log;
CREATE POLICY audit_log_tenant_read ON audit_log
    FOR SELECT TO authenticated
    USING (doctor_id = current_doctor_id());


DO $$
DECLARE
    unprotected TEXT;
BEGIN
    SELECT string_agg(c.relname, ', ' ORDER BY c.relname)
      INTO unprotected
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       -- 'r' ordinary table, 'p' partitioned table. RLS is set per partition
       -- root and matters equally there.
       AND c.relkind IN ('r', 'p')
       AND NOT c.relrowsecurity;

    IF unprotected IS NOT NULL THEN
        RAISE EXCEPTION
            'Row Level Security is not enabled on: %. Add it to 001_rls.sql '
            'with a policy before applying.', unprotected;
    END IF;
END
$$;

COMMIT;
