export interface CatalogueNode {
  subtype: string;
  label: string;
  method: string;
  description: string;
  params: Record<string, string>;
}

export interface NodeCatalogueCategory {
  category: string;
  nodeType: 'trigger' | 'action' | 'conditional' | 'endpoint';
  nodes: CatalogueNode[];
}

export interface WorkflowNodeData {
  label: string;
  method: string;
  description: string;
  subtype: string;
  params: Record<string, string>;
}

export const NODE_CATALOGUE: NodeCatalogueCategory[] = [
  {
    category: 'Triggers',
    nodeType: 'trigger',
    nodes: [
      {
        subtype: 'lab_event',
        label: 'Lab Event',
        method: 'handle_lab_event',
        description: 'Triggered when a lab result is received',
        params: { patient_id: '', report_type: '' },
      },
      {
        subtype: 'webhook',
        label: 'Webhook',
        method: 'handle_webhook',
        description: 'Triggered by an incoming webhook request',
        params: { source: '' },
      },
    ],
  },
  {
    category: 'Actions',
    nodeType: 'action',
    nodes: [
      {
        subtype: 'get_patient',
        label: 'Get Patient',
        method: 'get_patient_by_id',
        description: 'Fetch patient record from Supabase',
        params: { patient_id: '{{trigger.patient_id}}' },
      },
      {
        subtype: 'initiate_call',
        label: 'Initiate Call',
        method: 'initiate_outbound_call',
        description: 'Start an ElevenLabs outbound call via Twilio',
        params: { phone_number: '{{patient.phone_number}}', system_prompt: '' },
      },
      {
        subtype: 'create_call_record',
        label: 'Create Call Record',
        method: 'create_call_record',
        description: 'Save call record to Supabase',
        params: { patient_id: '', call_reason: '', conversation_id: '' },
      },
      {
        subtype: 'update_call_record',
        label: 'Update Call Record',
        method: 'update_call_record',
        description: 'Update call record with outcome data',
        params: { call_id: '', call_outcome: '', patient_confirmed: '' },
      },
      {
        subtype: 'create_calendar_event',
        label: 'Create Calendar Event',
        method: 'create_calendar_event',
        description: 'Add appointment to Google Calendar',
        params: { patient_name: '', doctor_name: '', date: '', time: '' },
      },
      {
        subtype: 'create_appointment',
        label: 'Create Appointment',
        method: 'create_appointment',
        description: 'Save appointment record to Supabase',
        params: { call_id: '', patient_id: '', date: '', time: '' },
      },
    ],
  },
  {
    category: 'Conditionals',
    nodeType: 'conditional',
    nodes: [
      {
        subtype: 'if_condition',
        label: 'If Condition',
        method: 'evaluate_condition',
        description: 'Branch workflow based on a custom condition',
        params: { condition: '' },
      },
      {
        subtype: 'patient_confirmed',
        label: 'Patient Confirmed?',
        method: 'check_patient_confirmed',
        description: 'True if patient confirmed an appointment',
        params: {},
      },
      {
        subtype: 'appointment_booked',
        label: 'Appointment Booked?',
        method: 'check_appointment_booked',
        description: "True if call_outcome is 'appointment_booked'",
        params: {},
      },
    ],
  },
  {
    category: 'Output',
    nodeType: 'endpoint',
    nodes: [
      {
        subtype: 'success',
        label: 'Success',
        method: 'return_success',
        description: 'End workflow with a success response',
        params: { message: 'Workflow completed successfully' },
      },
      {
        subtype: 'log_error',
        label: 'Log Error',
        method: 'log_error',
        description: 'Log an error and terminate the workflow',
        params: { message: '', level: 'error' },
      },
      {
        subtype: 'return_response',
        label: 'Return Response',
        method: 'return_response',
        description: 'Return a JSON response to the caller',
        params: { status: '200', data: '{}' },
      },
    ],
  },
];

export const CATEGORY_STYLES = {
  Triggers: {
    nodeBg: 'bg-blue-950/70',
    nodeBorder: 'border-blue-700/60',
    nodeSelectedBorder: 'border-blue-400',
    nodeSelectedShadow: 'shadow-blue-500/25',
    handleBg: '!bg-blue-500',
    handleBorder: '!border-blue-300',
    accent: 'text-blue-400',
    badge: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
    palette: 'bg-blue-950/40 border-blue-800/50 hover:bg-blue-900/50',
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
    accent: 'text-purple-400',
    badge: 'text-purple-400 bg-purple-500/10 border-purple-500/30',
    palette: 'bg-purple-950/40 border-purple-800/50 hover:bg-purple-900/50',
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
    accent: 'text-amber-400',
    badge: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
    palette: 'bg-amber-950/40 border-amber-800/50 hover:bg-amber-900/50',
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
    accent: 'text-gray-400',
    badge: 'text-gray-400 bg-gray-500/10 border-gray-500/30',
    palette: 'bg-gray-800/40 border-gray-600/50 hover:bg-gray-700/50',
    dot: 'bg-gray-500',
    icon: '■',
    label: 'Output',
  },
} as const;
