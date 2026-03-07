'use client';

import { Handle, Position, type NodeProps } from '@xyflow/react';
import { type WorkflowNodeData } from '../types';

const NODE_TYPE_STYLES: Record<
  string,
  { border: string; selectedBorder: string; shadow: string; icon: string; accent: string }
> = {
  log_completion: {
    border: 'border-emerald-200',
    selectedBorder: 'border-emerald-500',
    shadow: 'shadow-emerald-100',
    icon: '✓',
    accent: 'text-emerald-600',
  },
  send_summary_to_doctor: {
    border: 'border-gray-200',
    selectedBorder: 'border-gray-400',
    shadow: 'shadow-gray-100',
    icon: '↩',
    accent: 'text-gray-500',
  },
};

const DEFAULT_STYLE = NODE_TYPE_STYLES.log_completion;

export default function EndpointNode({ data, selected }: NodeProps) {
  const d = data as unknown as WorkflowNodeData;
  const style = NODE_TYPE_STYLES[d.nodeType] ?? DEFAULT_STYLE;

  return (
    <div
      className={`
        min-w-[176px] rounded-xl border-2 px-4 py-3
        bg-card
        transition-all duration-150
        ${selected
          ? `${style.selectedBorder} shadow-lg ${style.shadow}`
          : `${style.border} hover:brightness-95`
        }
      `}
    >
      {/* Target handle -- top center */}
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-gray-500 !border-2 !border-gray-300 !w-3 !h-3"
      />

      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <span className={`${style.accent} text-base font-bold leading-none`}>{style.icon}</span>
        <span className={`text-[10px] uppercase tracking-widest font-bold ${style.accent}`}>Output</span>
      </div>

      {/* Label */}
      <p className="text-sm font-semibold text-foreground leading-tight">{d.label}</p>

      {/* Node type */}
      <p className={`text-[11px] font-mono mt-1 truncate ${style.accent} opacity-50`}>{d.nodeType}</p>
    </div>
  );
}
