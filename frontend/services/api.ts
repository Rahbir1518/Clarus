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

export async function listCallLogs(workflowId?: string) {
  const params = new URLSearchParams();
  if (workflowId) params.set('workflow_id', workflowId);
  const qs = params.toString();
  const response = await fetch(`${API_URL}/api/call-logs${qs ? `?${qs}` : ''}`);
  return response.json();
}
