-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.
--
-- Generated snapshot of the live Supabase schema, kept because it is the
-- easiest way to read the column layout at a glance. It is NOT the source of
-- truth: a dump of this form omits indexes, triggers and ON DELETE behaviour,
-- so it cannot rebuild a working database.
--
-- Source of truth: 000_initial_schema.sql. Change the schema there.

CREATE TABLE public.doctors (
  id text NOT NULL,
  name text NOT NULL,
  email text,
  phone text,
  npi text,
  specialty text,
  practice_name text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT doctors_pkey PRIMARY KEY (id)
);
CREATE TABLE public.patients (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  doctor_id text NOT NULL,
  name text NOT NULL,
  phone text NOT NULL,
  email text,
  dob date,
  mrn text,
  insurance text,
  primary_physician text,
  last_visit date,
  risk_level text NOT NULL DEFAULT 'low'::text CHECK (risk_level = ANY (ARRAY['low'::text, 'moderate'::text, 'high'::text])),
  notes text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  deleted_at timestamp with time zone,
  CONSTRAINT patients_pkey PRIMARY KEY (id),
  CONSTRAINT patients_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.doctors(id)
);
CREATE TABLE public.workflows (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  doctor_id text NOT NULL,
  doctor_name text,
  name text NOT NULL,
  description text,
  category text,
  status text NOT NULL DEFAULT 'DRAFT'::text CHECK (status = ANY (ARRAY['DRAFT'::text, 'ENABLED'::text, 'ARCHIVED'::text])),
  nodes jsonb NOT NULL DEFAULT '[]'::jsonb,
  edges jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT workflows_pkey PRIMARY KEY (id),
  CONSTRAINT workflows_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.doctors(id)
);
CREATE TABLE public.call_logs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  doctor_id text NOT NULL,
  workflow_id uuid,
  patient_id uuid,
  trigger_node text,
  status text NOT NULL DEFAULT 'pending'::text,
  outcome text,
  keypress text,
  conversation_id text,
  transcript text,
  execution_log jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  deleted_at timestamp with time zone,
  CONSTRAINT call_logs_pkey PRIMARY KEY (id),
  CONSTRAINT call_logs_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.doctors(id),
  CONSTRAINT call_logs_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id),
  CONSTRAINT call_logs_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id)
);
CREATE TABLE public.appointments (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  doctor_id text NOT NULL,
  patient_id uuid NOT NULL,
  workflow_id uuid,
  call_log_id uuid,
  calendar_event_id text,
  starts_at timestamp with time zone NOT NULL,
  ends_at timestamp with time zone,
  status text NOT NULL DEFAULT 'scheduled'::text CHECK (status = ANY (ARRAY['scheduled'::text, 'confirmed'::text, 'completed'::text, 'cancelled'::text, 'no_show'::text])),
  location text,
  reason text,
  notes text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  deleted_at timestamp with time zone,
  CONSTRAINT appointments_pkey PRIMARY KEY (id),
  CONSTRAINT appointments_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.doctors(id),
  CONSTRAINT appointments_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id),
  CONSTRAINT appointments_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id),
  CONSTRAINT appointments_call_log_id_fkey FOREIGN KEY (call_log_id) REFERENCES public.call_logs(id)
);
CREATE TABLE public.patient_conditions (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL,
  icd10_code text NOT NULL,
  description text NOT NULL,
  hcc_category text,
  raf_impact numeric,
  status text NOT NULL DEFAULT 'documented'::text CHECK (status = ANY (ARRAY['documented'::text, 'review_needed'::text, 'pending_review'::text])),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  deleted_at timestamp with time zone,
  CONSTRAINT patient_conditions_pkey PRIMARY KEY (id),
  CONSTRAINT patient_conditions_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id)
);
CREATE TABLE public.patient_medications (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL,
  name text NOT NULL,
  dosage text,
  frequency text,
  route text,
  prescriber text,
  prescriber_doctor_id text,
  start_date date,
  end_date date,
  status text NOT NULL DEFAULT 'active'::text CHECK (status = ANY (ARRAY['active'::text, 'discontinued'::text, 'on_hold'::text])),
  notes text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  deleted_at timestamp with time zone,
  CONSTRAINT patient_medications_pkey PRIMARY KEY (id),
  CONSTRAINT patient_medications_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id),
  CONSTRAINT patient_medications_prescriber_doctor_id_fkey FOREIGN KEY (prescriber_doctor_id) REFERENCES public.doctors(id)
);
CREATE TABLE public.notifications (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  patient_id uuid,
  recipient text NOT NULL,
  message text NOT NULL,
  priority text NOT NULL DEFAULT 'normal'::text,
  status text NOT NULL DEFAULT 'unread'::text CHECK (status = ANY (ARRAY['unread'::text, 'read'::text])),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  read_at timestamp with time zone,
  CONSTRAINT notifications_pkey PRIMARY KEY (id),
  CONSTRAINT notifications_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id)
);
CREATE TABLE public.lab_orders (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  patient_id uuid,
  test_type text NOT NULL,
  priority text NOT NULL DEFAULT 'routine'::text,
  status text NOT NULL DEFAULT 'pending'::text CHECK (status = ANY (ARRAY['pending'::text, 'collected'::text, 'completed'::text, 'cancelled'::text])),
  notes text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  completed_at timestamp with time zone,
  deleted_at timestamp with time zone,
  CONSTRAINT lab_orders_pkey PRIMARY KEY (id),
  CONSTRAINT lab_orders_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id)
);
CREATE TABLE public.referrals (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  patient_id uuid,
  referring_doctor_id text,
  target_provider_name text,
  target_facility text,
  specialty text NOT NULL,
  reason text NOT NULL,
  urgency text NOT NULL DEFAULT 'routine'::text CHECK (urgency = ANY (ARRAY['routine'::text, 'urgent'::text, 'emergent'::text])),
  status text NOT NULL DEFAULT 'pending'::text CHECK (status = ANY (ARRAY['pending'::text, 'sent'::text, 'completed'::text, 'cancelled'::text])),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  completed_at timestamp with time zone,
  deleted_at timestamp with time zone,
  CONSTRAINT referrals_pkey PRIMARY KEY (id),
  CONSTRAINT referrals_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id),
  CONSTRAINT referrals_referring_doctor_id_fkey FOREIGN KEY (referring_doctor_id) REFERENCES public.doctors(id)
);
CREATE TABLE public.staff_assignments (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  patient_id uuid,
  staff_id text NOT NULL,
  task_type text NOT NULL,
  due_date date,
  status text NOT NULL DEFAULT 'assigned'::text CHECK (status = ANY (ARRAY['assigned'::text, 'in_progress'::text, 'completed'::text, 'cancelled'::text])),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  completed_at timestamp with time zone,
  CONSTRAINT staff_assignments_pkey PRIMARY KEY (id),
  CONSTRAINT staff_assignments_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id)
);
CREATE TABLE public.reports (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workflow_id uuid,
  patient_id uuid,
  call_log_id uuid,
  report_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT reports_pkey PRIMARY KEY (id),
  CONSTRAINT reports_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id),
  CONSTRAINT reports_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id),
  CONSTRAINT reports_call_log_id_fkey FOREIGN KEY (call_log_id) REFERENCES public.call_logs(id)
);
CREATE TABLE public.pdf_documents (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  patient_id uuid,
  filename text NOT NULL,
  file_url text,
  page_count integer,
  raw_text text,
  patient_info jsonb NOT NULL DEFAULT '{}'::jsonb,
  lab_results jsonb NOT NULL DEFAULT '[]'::jsonb,
  tables_data jsonb NOT NULL DEFAULT '[]'::jsonb,
  uploaded_by text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  deleted_at timestamp with time zone,
  CONSTRAINT pdf_documents_pkey PRIMARY KEY (id),
  CONSTRAINT pdf_documents_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id)
);
CREATE TABLE public.audit_log (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  doctor_id text,
  actor text NOT NULL,
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_id uuid,
  patient_id uuid,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT audit_log_pkey PRIMARY KEY (id),
  CONSTRAINT audit_log_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.doctors(id)
);