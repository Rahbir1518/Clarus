// ---------------------------------------------------------------------------
// The `nodeType` field is the dispatch key used by the backend workflow engine
// (workflow_engine.py). It MUST match one of:
//   TRIGGER_TYPES, ACTION_TYPES, CONDITION_TYPES, or OUTPUT_TYPES
// React Flow uses the top-level `type` field for rendering (trigger | action |
// conditional | endpoint), while `data.nodeType` tells the engine what to do.
// ---------------------------------------------------------------------------

export interface CatalogueNode {
  nodeType: string;             // backend dispatch key (e.g. "call_patient")
  label: string;                // UI display name
  description: string;
  params: Record<string, string>;
}

export interface NodeCatalogueCategory {
  category: string;
  /** React Flow custom node component type */
  reactFlowType: 'trigger' | 'action' | 'conditional' | 'endpoint';
  nodes: CatalogueNode[];
}

export interface WorkflowNodeData {
  label: string;
  nodeType: string;             // backend dispatch key
  description: string;
  params: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Node catalogue — every entry corresponds to a type recognised by the
// backend's workflow_engine.py dispatch table.
// ---------------------------------------------------------------------------

export const NODE_CATALOGUE: NodeCatalogueCategory[] = [
  {
    category: 'Triggers',
    reactFlowType: 'trigger',
    nodes: [
      {
        nodeType: 'lab_results_received',
        label: 'Lab Results Received',
        description: 'Triggered when lab results arrive for a patient',
        params: {},
      },
      {
        nodeType: 'abnormal_result_detected',
        label: 'Abnormal Result',
        description: 'Triggered when an abnormal lab value is detected',
        params: {},
      },
      {
        nodeType: 'follow_up_due',
        label: 'Follow-Up Due',
        description: 'Triggered when a patient is due for a follow-up visit',
        params: {},
      },
      {
        nodeType: 'appointment_missed',
        label: 'Appointment Missed',
        description: 'Triggered when a patient misses a scheduled appointment',
        params: {},
      },
      {
        nodeType: 'new_patient_registered',
        label: 'New Patient Registered',
        description: 'Triggered when a new patient is registered in the system',
        params: {},
      },
      {
        nodeType: 'prescription_expiring',
        label: 'Prescription Expiring',
        description: 'Triggered when a patient prescription is about to expire',
        params: {},
      },
    ],
  },
  {
    category: 'Actions',
    reactFlowType: 'action',
    nodes: [
      {
        nodeType: 'call_patient',
        label: 'Call Patient',
        description: 'Place an AI-powered outbound call to the patient via ElevenLabs + Twilio',
        params: { lab_result_summary: '' },
      },
      {
        nodeType: 'send_sms',
        label: 'Send SMS',
        description: 'Send an SMS message to the patient via Twilio',
        params: { message: '' },
      },
      {
        nodeType: 'schedule_appointment',
        label: 'Schedule Appointment',
        description: 'Schedule a follow-up appointment on Google Calendar',
        params: {},
      },
      {
        nodeType: 'send_notification',
        label: 'Send Notification',
        description: 'Send an internal notification to staff members',
        params: { message: '', recipient: 'staff', priority: 'normal' },
      },
      {
        nodeType: 'create_lab_order',
        label: 'Create Lab Order',
        description: 'Create a new lab order for the patient',
        params: { test_type: '', priority: 'routine', notes: '' },
      },
      {
        nodeType: 'create_referral',
        label: 'Create Referral',
        description: 'Create a specialist referral for the patient',
        params: { specialty: '', reason: '', urgency: 'routine' },
      },
      {
        nodeType: 'update_patient_record',
        label: 'Update Patient Record',
        description: 'Update specific fields on the patient record',
        params: { risk_level: '', notes: '' },
      },
      {
        nodeType: 'assign_to_staff',
        label: 'Assign to Staff',
        description: 'Assign the patient to a staff member for follow-up',
        params: { staff_id: '', task_type: 'follow_up', due_date: '' },
      },
    ],
  },
  {
    category: 'Conditionals',
    reactFlowType: 'conditional',
    nodes: [
      {
        nodeType: 'check_result_values',
        label: 'Check Result Values',
        description: 'Branch based on whether lab results meet a threshold',
        params: { test_name: '', operator: 'greater_than', threshold: '', threshold_max: '' },
      },
      {
        nodeType: 'check_insurance',
        label: 'Check Insurance',
        description: 'Branch based on patient insurance status',
        params: { insurance_type: 'any' },
      },
      {
        nodeType: 'check_patient_age',
        label: 'Check Patient Age',
        description: 'Branch based on patient age range',
        params: { operator: 'greater_than', threshold: '', threshold_max: '' },
      },
      {
        nodeType: 'check_appointment_history',
        label: 'Check Appointment History',
        description: 'Branch based on how long since the last appointment',
        params: { days_since_last: '90' },
      },
      {
        nodeType: 'check_medication_list',
        label: 'Check Medication List',
        description: 'Branch based on whether patient is on specific medications',
        params: { medication: '' },
      },
    ],
  },
  {
    category: 'Output',
    reactFlowType: 'endpoint',
    nodes: [
      {
        nodeType: 'log_completion',
        label: 'Log Completion',
        description: 'Log that the workflow completed successfully',
        params: {},
      },
      {
        nodeType: 'generate_transcript',
        label: 'Generate Transcript',
        description: 'Fetch and store the AI call transcript from ElevenLabs',
        params: {},
      },
      {
        nodeType: 'create_report',
        label: 'Create Report',
        description: 'Generate a structured execution report for review',
        params: {},
      },
      {
        nodeType: 'send_summary_to_doctor',
        label: 'Send Summary to Doctor',
        description: 'Send the workflow execution summary to the doctor',
        params: {},
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Visual styles per category — used by node components, palette, and panel
// ---------------------------------------------------------------------------

export const CATEGORY_STYLES = {
  Triggers: {
    nodeBg: 'bg-blue-950/70',
    nodeBorder: 'border-blue-700/60',
    nodeSelectedBorder: 'border-blue-400',
    nodeSelectedShadow: 'shadow-blue-500/25',
    handleBg: '!bg-blue-500',
    handleBorder: '!border-blue-300',
    accent: 'text-blue-600',
    badge: 'text-blue-600 bg-blue-50 border-blue-200',
    palette: 'bg-blue-50 border-blue-200 hover:bg-blue-100',
    dot: 'bg-blue-500',
    icon: '⚡',
    label: 'Trigger',
  },
  Actions: {
    nodeBg: 'bg-purple-950/70',
    nodeBorder: 'border-purple-700/60',
    nodeSelectedBorder: 'border-purple-400',
    nodeSelectedShadow: 'shadow-purple-500/25',
    handleBg: '!bg-purple-500',
    handleBorder: '!border-purple-300',
    accent: 'text-purple-600',
    badge: 'text-purple-600 bg-purple-50 border-purple-200',
    palette: 'bg-purple-50 border-purple-200 hover:bg-purple-100',
    dot: 'bg-purple-500',
    icon: '⚙',
    label: 'Action',
  },
  Conditionals: {
    nodeBg: 'bg-amber-950/70',
    nodeBorder: 'border-amber-700/60',
    nodeSelectedBorder: 'border-amber-400',
    nodeSelectedShadow: 'shadow-amber-500/25',
    handleBg: '!bg-amber-500',
    handleBorder: '!border-amber-300',
    accent: 'text-amber-600',
    badge: 'text-amber-600 bg-amber-50 border-amber-200',
    palette: 'bg-amber-50 border-amber-200 hover:bg-amber-100',
    dot: 'bg-amber-500',
    icon: '◇',
    label: 'Condition',
  },
  Output: {
    nodeBg: 'bg-gray-800/70',
    nodeBorder: 'border-gray-600/60',
    nodeSelectedBorder: 'border-gray-400',
    nodeSelectedShadow: 'shadow-gray-500/25',
    handleBg: '!bg-gray-500',
    handleBorder: '!border-gray-300',
    accent: 'text-gray-500',
    badge: 'text-gray-600 bg-gray-50 border-gray-200',
    palette: 'bg-gray-50 border-gray-200 hover:bg-gray-100',
    dot: 'bg-gray-500',
    icon: '■',
    label: 'Output',
  },
} as const;
