'use client';

import { Handle, Position, type NodeProps } from '@xyflow/react';
import { type WorkflowNodeData } from '../types';

const NODE_TYPE_STYLES: Record<
  string,
  { bg: string; border: string; selectedBorder: string; shadow: string; icon: string; accent: string }
> = {
  log_completion: {
    bg: 'bg-emerald-950/70',
    border: 'border-emerald-700/60',
    selectedBorder: 'border-emerald-400',
    shadow: 'shadow-emerald-500/25',
    icon: '✓',
    accent: 'text-emerald-400',
  },
  send_summary_to_doctor: {
    bg: 'bg-gray-800/70',
    border: 'border-gray-600/60',
    selectedBorder: 'border-gray-400',
    shadow: 'shadow-gray-500/25',
    icon: '↩',
    accent: 'text-gray-400',
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
        ${style.bg}
        transition-all duration-150
        ${selected
          ? `${style.selectedBorder} shadow-xl ${style.shadow}`
          : `${style.border} hover:brightness-110`
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
      <p className="text-sm font-semibold text-white leading-tight">{d.label}</p>

      {/* Node type */}
      <p className={`text-[11px] font-mono mt-1 truncate ${style.accent} opacity-50`}>{d.nodeType}</p>
    </div>
  );
}
