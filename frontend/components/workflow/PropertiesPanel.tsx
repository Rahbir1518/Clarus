'use client';

import { type Node } from '@xyflow/react';
import { CATEGORY_STYLES, type WorkflowNodeData } from './types';

const NODE_TYPE_CATEGORY: Record<string, keyof typeof CATEGORY_STYLES> = {
  trigger: 'Triggers',
  action: 'Actions',
  conditional: 'Conditionals',
  endpoint: 'Output',
};

const OPERATOR_OPTIONS = [
  { value: 'greater_than', label: 'Greater than' },
  { value: 'less_than', label: 'Less than' },
  { value: 'equal_to', label: 'Equal to' },
  { value: 'between', label: 'Between' },
  { value: 'in_range', label: 'In range' },
  { value: 'out_of_range', label: 'Out of range' },
];

const PRIORITY_OPTIONS = [
  { value: 'normal', label: 'Normal' },
  { value: 'urgent', label: 'Urgent' },
  { value: 'routine', label: 'Routine' },
  { value: 'stat', label: 'STAT' },
];

const URGENCY_OPTIONS = [
  { value: 'routine', label: 'Routine' },
  { value: 'urgent', label: 'Urgent' },
  { value: 'emergent', label: 'Emergent' },
];

const SELECT_FIELDS: Record<string, { label: string; value: string }[]> = {
  operator: OPERATOR_OPTIONS,
  priority: PRIORITY_OPTIONS,
  urgency: URGENCY_OPTIONS,
};

const FIELD_LABELS: Record<string, string> = {
  test_name: 'Lab Test Name',
  operator: 'Operator',
  threshold: 'Threshold',
  threshold_max: 'Max Threshold',
  insurance_type: 'Insurance Type',
  days_since_last: 'Days Since Last',
  medication: 'Medication Name(s)',
  message: 'Message',
  recipient: 'Recipient',
  priority: 'Priority',
  test_type: 'Test Type',
  notes: 'Notes',
  specialty: 'Specialty',
  reason: 'Reason',
  urgency: 'Urgency',
  staff_id: 'Staff ID',
  task_type: 'Task Type',
  due_date: 'Due Date',
  risk_level: 'Risk Level',
  lab_result_summary: 'Lab Result Summary',
};

const FIELD_PLACEHOLDERS: Record<string, string> = {
  test_name: 'e.g. Glucose, HbA1c',
  threshold: 'e.g. 100',
  threshold_max: 'e.g. 200',
  insurance_type: '"any" or provider name',
  days_since_last: 'e.g. 90',
  medication: 'e.g. metformin, lisinopril',
  message: 'Enter message text...',
  recipient: 'e.g. staff, nurse_station',
  test_type: 'e.g. CBC, Metabolic Panel',
  notes: 'Additional notes...',
  specialty: 'e.g. Cardiology, Endocrinology',
  reason: 'Reason for referral...',
  staff_id: 'Staff member ID',
  task_type: 'e.g. follow_up, review',
  due_date: 'YYYY-MM-DD',
  risk_level: 'low, medium, or high',
  lab_result_summary: 'Summary for the AI call agent...',
};

interface Props {
  selectedNode: Node | null;
  onUpdateParams: (nodeId: string, params: Record<string, string>) => void;
  onDeleteNode: (nodeId: string) => void;
}

export function PropertiesPanel({ selectedNode, onUpdateParams, onDeleteNode }: Props) {
  if (!selectedNode) {
    return (
      <aside className="w-64 shrink-0 border-l border-border bg-card flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-border shrink-0">
          <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Properties</p>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center gap-2 p-6">
          <div className="w-8 h-8 rounded-lg border-2 border-dashed border-border flex items-center justify-center">
            <span className="text-muted-foreground text-xs">↖</span>
          </div>
          <p className="text-[11px] text-muted-foreground text-center leading-relaxed">
            Click a node to inspect and edit its properties
          </p>
        </div>
      </aside>
    );
  }

  const categoryKey = NODE_TYPE_CATEGORY[selectedNode.type ?? ''] ?? 'Actions';
  const styles = CATEGORY_STYLES[categoryKey];
  const data = selectedNode.data as unknown as WorkflowNodeData;
  const params = data.params ?? {};

  const handleParamChange = (key: string, value: string) => {
    onUpdateParams(selectedNode.id, { ...params, [key]: value });
  };

  const renderParamInput = (key: string, value: string) => {
    const selectOptions = SELECT_FIELDS[key];
    const label = FIELD_LABELS[key] || key;
    const placeholder = FIELD_PLACEHOLDERS[key] || `{{${key}}}`;

    if (selectOptions) {
      return (
        <div key={key}>
          <label className="block text-[10px] text-muted-foreground font-medium mb-1">{label}</label>
          <select
            value={value}
            onChange={(e) => handleParamChange(key, e.target.value)}
            className="
              w-full text-xs bg-background border border-input rounded-lg
              px-3 py-2 text-foreground
              focus:outline-none focus:border-ring focus:ring-1 focus:ring-ring/30
              transition-colors
            "
          >
            {selectOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      );
    }

    if (key === 'message' || key === 'reason' || key === 'notes' || key === 'lab_result_summary') {
      return (
        <div key={key}>
          <label className="block text-[10px] text-muted-foreground font-medium mb-1">{label}</label>
          <textarea
            value={value}
            onChange={(e) => handleParamChange(key, e.target.value)}
            rows={3}
            className="
              w-full text-xs bg-background border border-input rounded-lg
              px-3 py-2 text-foreground font-mono resize-y
              focus:outline-none focus:border-ring focus:ring-1 focus:ring-ring/30
              placeholder-muted-foreground transition-colors
            "
            placeholder={placeholder}
          />
        </div>
      );
    }

    return (
      <div key={key}>
        <label className="block text-[10px] text-muted-foreground font-medium mb-1">{label}</label>
        <input
          type={key === 'due_date' ? 'date' : key.includes('threshold') || key === 'days_since_last' ? 'number' : 'text'}
          value={value}
          onChange={(e) => handleParamChange(key, e.target.value)}
          className="
            w-full text-xs bg-background border border-input rounded-lg
            px-3 py-2 text-foreground font-mono
            focus:outline-none focus:border-ring focus:ring-1 focus:ring-ring/30
            placeholder-muted-foreground transition-colors
          "
          placeholder={placeholder}
        />
      </div>
    );
  };

  return (
    <aside className="w-64 shrink-0 border-l border-border bg-card flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border shrink-0">
        <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Properties</p>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        {/* Type badge */}
        <span
          className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide border ${styles.badge}`}
        >
          <span>{styles.icon}</span>
          {styles.label}
        </span>

        {/* Label */}
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1.5">Label</p>
          <p className="text-sm font-semibold text-foreground">{data.label}</p>
        </div>

        {/* Node Type */}
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1.5">Node Type</p>
          <code className="block text-xs font-mono text-primary bg-muted px-3 py-2 rounded-lg break-all">
            {data.nodeType}
          </code>
        </div>

        {/* Description */}
        {data.description ? (
          <div>
            <p className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1.5">Description</p>
            <p className="text-xs text-muted-foreground leading-relaxed">{data.description}</p>
          </div>
        ) : null}

        {/* Parameters */}
        {Object.keys(params).length > 0 && (
          <div>
            <p className="text-[10px] text-muted-foreground uppercase tracking-widest mb-2.5">Parameters</p>
            <div className="space-y-3">
              {Object.entries(params).map(([key, value]) => renderParamInput(key, value))}
            </div>
          </div>
        )}

        {/* Divider */}
        <div className="border-t border-border" />

        {/* Node ID */}
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">Node ID</p>
          <code className="text-[10px] text-muted-foreground font-mono break-all">{selectedNode.id}</code>
        </div>

        {/* Delete button */}
        <button
          onClick={() => onDeleteNode(selectedNode.id)}
          className="
            w-full px-3 py-2 rounded-lg border border-destructive/30 text-destructive
            text-xs font-medium
            hover:bg-destructive/10 hover:border-destructive/50
            transition-colors duration-150
          "
        >
          Delete Node
        </button>
      </div>
    </aside>
  );
}
