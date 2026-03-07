'use client';

import { Handle, Position, type NodeProps } from '@xyflow/react';
import { type WorkflowNodeData } from '../types';

const SUBTYPE_STYLES: Record<
  string,
  { bg: string; border: string; selectedBorder: string; shadow: string; icon: string; accent: string }
> = {
  success: {
    bg: 'bg-emerald-950/70',
    border: 'border-emerald-700/60',
    selectedBorder: 'border-emerald-400',
    shadow: 'shadow-emerald-500/25',
    icon: '✓',
    accent: 'text-emerald-400',
  },
  log_error: {
    bg: 'bg-red-950/70',
    border: 'border-red-700/60',
    selectedBorder: 'border-red-400',
    shadow: 'shadow-red-500/25',
    icon: '✗',
    accent: 'text-red-400',
  },
  return_response: {
    bg: 'bg-gray-800/70',
    border: 'border-gray-600/60',
    selectedBorder: 'border-gray-400',
    shadow: 'shadow-gray-500/25',
    icon: '↩',
    accent: 'text-gray-400',
  },
};

export default function EndpointNode({ data, selected }: NodeProps) {
  const d = data as unknown as WorkflowNodeData;
  const style = SUBTYPE_STYLES[d.subtype] ?? SUBTYPE_STYLES.return_response;

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
      {/* Target handle — top center */}
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

      {/* Method */}
      <p className={`text-[11px] font-mono mt-1 truncate ${style.accent} opacity-50`}>{d.method}()</p>
    </div>
  );
}
