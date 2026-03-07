// This is api.ts and this is used for handling requests to the FastAPI backend.

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Lab event
// ---------------------------------------------------------------------------

export async function simulateLabEvent(
  triggerType: string,
  patientId: string,
  doctorId?: string,
  metadata?: Record<string, unknown>,
) {
  const response = await fetch(`${API_URL}/api/lab-event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      trigger_type: triggerType,
      patient_id: patientId,
      doctor_id: doctorId ?? null,
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

export async function executeWorkflow(
  workflowId: string,
  patientId: string,
  triggerNodeType?: string,
) {
  const response = await fetch(`${API_URL}/api/workflows/${workflowId}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      patient_id: patientId,
      trigger_node_type: triggerNodeType ?? null,
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
