// This is api.ts and this is used for handling requests to the FastAPI backend.

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Authentication
//
// Every request to the backend needs a Clerk session token; without one the
// API answers 401. Rather than thread a token through thirty-five call sites —
// where the one that gets missed is a silent bug — `fetch` below SHADOWS the
// global `fetch` for this entire module. Calls read exactly as they always
// did, and there is no version of them that forgets the header.
//
// Clerk's `getToken` lives behind a React hook, which a plain module cannot
// call. ClerkTokenBridge (mounted once in app/layout.tsx) registers it here at
// startup; see app/providers/ClerkTokenBridge.tsx.
// ---------------------------------------------------------------------------

type TokenGetter = () => Promise<string | null>;

let getAuthToken: TokenGetter | null = null;

export function setAuthTokenGetter(getter: TokenGetter | null) {
  getAuthToken = getter;
}

async function fetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  // Clerk session tokens expire after about a minute and the SDK refreshes
  // them in the background, so fetch one per request rather than caching.
  const token = getAuthToken ? await getAuthToken() : null;

  const headers = new Headers(init.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  // Deliberately no Content-Type default: the upload calls send FormData, and
  // setting it by hand would clobber the multipart boundary the browser adds.
  return globalThis.fetch(input, { ...init, headers });
}

// The event stream needs the same header on a request this module does not
// make. Exported rather than duplicated: a second copy of the token logic is a
// second place for it to drift.
export { fetch as authorizedFetch };

// ---------------------------------------------------------------------------
// Lab event
// ---------------------------------------------------------------------------

/**
 * Fire one trigger and let every enabled workflow that listens for it run.
 *
 * `matched: 0` is an ordinary answer — an event nothing subscribes to is not an
 * error. `unrunnable` lists enabled workflows that listen for this trigger but
 * whose graph could not be walked, so a broken workflow is visible rather than
 * silently never firing.
 *
 * No doctor_id: the tenant comes from the session token, as it does everywhere.
 */
export async function simulateLabEvent(
  triggerType: string,
  patientId: string,
  metadata?: Record<string, unknown>,
): Promise<{
  trigger_type: string;
  patient_id: string;
  matched: number;
  runs: WorkflowRun[];
  unrunnable: { workflow_id: string; name: string | null; reason: string }[];
}> {
  const response = await fetch(`${API_URL}/api/lab-event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      trigger_type: triggerType,
      patient_id: patientId,
      metadata: metadata ?? {},
    }),
  });
  return response.json();
}

// ---------------------------------------------------------------------------
// Workflow CRUD
// ---------------------------------------------------------------------------

export async function listWorkflows(doctorId?: string, status?: string) {
  const params = new URLSearchParams();
  if (doctorId) params.set('doctor_id', doctorId);
  if (status) params.set('status', status);
  const qs = params.toString();
  const response = await fetch(`${API_URL}/api/workflows${qs ? `?${qs}` : ''}`);
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(`Failed to fetch workflows (${response.status}): ${detail}`);
  }
  return response.json();
}

export async function getWorkflow(workflowId: string) {
  const response = await fetch(`${API_URL}/api/workflows/${workflowId}`);
  return response.json();
}

export async function createWorkflow(payload: {
  doctor_id: string;
  name: string;
  description?: string;
  category?: string;
  status?: string;
  nodes?: unknown[];
  edges?: unknown[];
}) {
  const response = await fetch(`${API_URL}/api/workflows`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return response.json();
}

export async function updateWorkflow(
  workflowId: string,
  payload: {
    name?: string;
    description?: string;
    category?: string;
    status?: string;
    nodes?: unknown[];
    edges?: unknown[];
  },
) {
  const response = await fetch(`${API_URL}/api/workflows/${workflowId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return response.json();
}

export async function deleteWorkflow(workflowId: string) {
  const response = await fetch(`${API_URL}/api/workflows/${workflowId}`, {
    method: 'DELETE',
  });
  return response;
}

// ---------------------------------------------------------------------------
// Patients
// ---------------------------------------------------------------------------

export async function listPatients(doctorId?: string) {
  const params = new URLSearchParams();
  if (doctorId) params.set('doctor_id', doctorId);
  const qs = params.toString();
  const response = await fetch(`${API_URL}/api/patients${qs ? `?${qs}` : ''}`);
  return response.json();
}

export async function getPatient(patientId: string) {
  const response = await fetch(`${API_URL}/api/patients/${patientId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch patient (${response.status})`);
  }
  return response.json();
}

export async function createPatient(payload: {
  name: string;
  phone: string;
  doctor_id: string;
}) {
  const response = await fetch(`${API_URL}/api/patients`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return response.json();
}

export async function updatePatient(
  patientId: string,
  payload: {
    name?: string;
    phone?: string;
    dob?: string | null;
    mrn?: string | null;
    insurance?: string | null;
    primary_physician?: string | null;
    last_visit?: string | null;
    risk_level?: string;
    notes?: string | null;
  },
) {
  const response = await fetch(`${API_URL}/api/patients/${patientId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return response.json();
}

export async function deletePatient(patientId: string) {
  const response = await fetch(`${API_URL}/api/patients/${patientId}`, {
    method: 'DELETE',
  });
  return response;
}

// ---------------------------------------------------------------------------
// Patient conditions
// ---------------------------------------------------------------------------

export async function listConditions(patientId: string) {
  const response = await fetch(`${API_URL}/api/patients/${patientId}/conditions`);
  return response.json();
}

export async function createCondition(
  patientId: string,
  payload: {
    icd10_code: string;
    description: string;
    hcc_category?: string;
    raf_impact?: number;
    status?: string;
  },
) {
  const response = await fetch(`${API_URL}/api/patients/${patientId}/conditions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return response.json();
}

export async function updateCondition(
  patientId: string,
  conditionId: string,
  payload: {
    icd10_code?: string;
    description?: string;
    hcc_category?: string;
    raf_impact?: number;
    status?: string;
  },
) {
  const response = await fetch(`${API_URL}/api/patients/${patientId}/conditions/${conditionId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return response.json();
}

export async function deleteCondition(patientId: string, conditionId: string) {
  const response = await fetch(`${API_URL}/api/patients/${patientId}/conditions/${conditionId}`, {
    method: 'DELETE',
  });
  return response;
}

// ---------------------------------------------------------------------------
// Execute workflow
// ---------------------------------------------------------------------------

/** One entry in a run's execution log. Shape defined in backend/app/engine/steps.py. */
export type ExecutionStep = {
  seq: number;
  node_id: string | null;
  node_type: string;
  label: string;
  /** ok | skipped | blocked | failed | parked */
  status: string;
  message: string;
  at: string;
  branch: 'true' | 'false' | null;
  entity: { table: string; id: string } | null;
};

export type WorkflowRun = {
  call_log_id: string;
  /** completed | parked | failed | blocked. `parked` means a call is in flight. */
  status: string;
  execution_log: ExecutionStep[];
  workflow_id: string | null;
};

/**
 * Run one workflow against one patient.
 *
 * `metadata` is the body of the event that would have fired the trigger — lab
 * values, and an `abnormal` flag. Conditionals read it. None of it is ever
 * spoken to the patient, which is why free-form data is safe here.
 */
export async function executeWorkflow(
  workflowId: string,
  patientId: string,
  triggerNodeType?: string,
  metadata?: Record<string, unknown>,
): Promise<WorkflowRun> {
  const response = await fetch(`${API_URL}/api/workflows/${workflowId}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      patient_id: patientId,
      trigger_node_type: triggerNodeType ?? null,
      metadata: metadata ?? {},
    }),
  });
  return response.json();
}

// ---------------------------------------------------------------------------
// Call logs
// ---------------------------------------------------------------------------

export async function listCallLogs(workflowId?: string, doctorId?: string) {
  const params = new URLSearchParams();
  if (workflowId) params.set('workflow_id', workflowId);
  if (doctorId) params.set('doctor_id', doctorId);
  const qs = params.toString();
  const response = await fetch(`${API_URL}/api/call-logs${qs ? `?${qs}` : ''}`);
  return response.json();
}

export async function checkCallStatus(callLogId: string) {
  const response = await fetch(`${API_URL}/api/call-logs/${callLogId}/check`, {
    method: 'POST',
  });
  return response.json();
}

// ---------------------------------------------------------------------------
// Placing calls
//
// Two steps because a WebRTC session is opened by the browser, so ElevenLabs
// mints the conversation id here rather than on the server. Until bindCall
// reports it back, the post-call webhook has no row to resolve and the
// outcome is discarded — so bind on connect, not on hang-up.
// ---------------------------------------------------------------------------

export type WebCallStarted = {
  call_log_id: string;
  token: string;
  // Every {{placeholder}} the agent speaks. Built server-side from the patient
  // record; the browser passes it through untouched and must not edit it.
  dynamic_variables: Record<string, string>;
};

// The reasons a patient may be given for a call, and the whole set of them.
// Mirrors ALLOWED_CALL_REASONS in backend/app/engine/policy.py; anything else is
// a 422. There is no free-text alternative on purpose — the agent never
// discloses a clinical result, and a sentence field is how one would get said.
export type CallReasonCode =
  | 'results_ready'
  | 'follow_up'
  | 'annual_check_up'
  | 'medication_review'
  | 'appointment_confirmation'
  | 'missed_appointment';

export async function startWebCall(
  patientId: string,
  options: { workflowId?: string; reasonCode?: CallReasonCode } = {},
): Promise<WebCallStarted> {
  const response = await fetch(`${API_URL}/api/calls/web`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      patient_id: patientId,
      workflow_id: options.workflowId,
      reason_code: options.reasonCode,
    }),
  });
  if (!response.ok) throw new Error(`Could not start the call (${response.status})`);
  return response.json();
}

export async function bindCall(callLogId: string, conversationId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/calls/web/${callLogId}/bind`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId }),
  });
  // 409 means this call log is already bound to a different conversation.
  if (!response.ok) throw new Error(`Could not bind the conversation (${response.status})`);
}

// ---------------------------------------------------------------------------
// Patient medications
// ---------------------------------------------------------------------------

export async function listMedications(patientId: string) {
  const response = await fetch(`${API_URL}/api/patients/${patientId}/medications`);
  return response.json();
}

export async function createMedication(
  patientId: string,
  payload: {
    name: string;
    dosage?: string;
    frequency?: string;
    route?: string;
    prescriber?: string;
    start_date?: string;
    end_date?: string;
    status?: string;
    notes?: string;
  },
) {
  const response = await fetch(`${API_URL}/api/patients/${patientId}/medications`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return response.json();
}

export async function updateMedication(
  patientId: string,
  medicationId: string,
  payload: {
    name?: string;
    dosage?: string;
    frequency?: string;
    route?: string;
    prescriber?: string;
    start_date?: string;
    end_date?: string;
    status?: string;
    notes?: string;
  },
) {
  const response = await fetch(`${API_URL}/api/patients/${patientId}/medications/${medicationId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return response.json();
}

export async function deleteMedication(patientId: string, medicationId: string) {
  const response = await fetch(`${API_URL}/api/patients/${patientId}/medications/${medicationId}`, {
    method: 'DELETE',
  });
  return response;
}

// ---------------------------------------------------------------------------
// PDF upload & extraction
// ---------------------------------------------------------------------------

export async function uploadPdf(
  file: File,
  patientId?: string,
  uploadedBy?: string,
) {
  const formData = new FormData();
  formData.append('file', file);
  if (patientId) formData.append('patient_id', patientId);
  if (uploadedBy) formData.append('uploaded_by', uploadedBy);

  const response = await fetch(`${API_URL}/api/pdf/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(`PDF upload failed (${response.status}): ${detail}`);
  }
  return response.json();
}

export async function pdfIntake(file: File, doctorId: string) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('doctor_id', doctorId);

  const response = await fetch(`${API_URL}/api/pdf/intake`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(`PDF intake failed (${response.status}): ${detail}`);
  }
  return response.json();
}

export async function importPdfToPatient(file: File, patientId: string) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_URL}/api/patients/${patientId}/import-pdf`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(`PDF import failed (${response.status}): ${detail}`);
  }
  return response.json();
}

export async function extractPdfAndExecute(
  file: File,
  patientId: string,
  workflowId: string,
) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('patient_id', patientId);
  formData.append('workflow_id', workflowId);

  const response = await fetch(`${API_URL}/api/pdf/extract-and-execute`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(`PDF extract & execute failed (${response.status}): ${detail}`);
  }
  return response.json();
}

export async function listPdfDocuments(patientId?: string) {
  const params = new URLSearchParams();
  if (patientId) params.set('patient_id', patientId);
  const qs = params.toString();
  const response = await fetch(`${API_URL}/api/pdf/documents${qs ? `?${qs}` : ''}`);
  return response.json();
}

export async function getPdfDocument(docId: string) {
  const response = await fetch(`${API_URL}/api/pdf/documents/${docId}`);
  if (!response.ok) throw new Error(`Failed to fetch PDF document (${response.status})`);
  return response.json();
}

export async function deletePdfDocument(docId: string) {
  return fetch(`${API_URL}/api/pdf/documents/${docId}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

export async function listNotifications(patientId?: string) {
  const params = new URLSearchParams();
  if (patientId) params.set('patient_id', patientId);
  const qs = params.toString();
  const response = await fetch(`${API_URL}/api/notifications${qs ? `?${qs}` : ''}`);
  return response.json();
}

// ---------------------------------------------------------------------------
// Lab orders
// ---------------------------------------------------------------------------

export async function listLabOrders(patientId?: string) {
  const params = new URLSearchParams();
  if (patientId) params.set('patient_id', patientId);
  const qs = params.toString();
  const response = await fetch(`${API_URL}/api/lab-orders${qs ? `?${qs}` : ''}`);
  return response.json();
}

// ---------------------------------------------------------------------------
// Referrals
// ---------------------------------------------------------------------------

export async function listReferrals(patientId?: string) {
  const params = new URLSearchParams();
  if (patientId) params.set('patient_id', patientId);
  const qs = params.toString();
  const response = await fetch(`${API_URL}/api/referrals${qs ? `?${qs}` : ''}`);
  return response.json();
}

// ---------------------------------------------------------------------------
// Staff assignments
// ---------------------------------------------------------------------------

export async function listStaffAssignments(patientId?: string, staffId?: string) {
  const params = new URLSearchParams();
  if (patientId) params.set('patient_id', patientId);
  if (staffId) params.set('staff_id', staffId);
  const qs = params.toString();
  const response = await fetch(`${API_URL}/api/staff-assignments${qs ? `?${qs}` : ''}`);
  return response.json();
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export async function listReports(patientId?: string, workflowId?: string) {
  const params = new URLSearchParams();
  if (patientId) params.set('patient_id', patientId);
  if (workflowId) params.set('workflow_id', workflowId);
  const qs = params.toString();
  const response = await fetch(`${API_URL}/api/reports${qs ? `?${qs}` : ''}`);
  return response.json();
}

export async function getReport(reportId: string) {
  const response = await fetch(`${API_URL}/api/reports/${reportId}`);
  if (!response.ok) throw new Error(`Failed to fetch report (${response.status})`);
  return response.json();
}
