'use client';

import { Handle, Position, type NodeProps } from '@xyflow/react';
import { type WorkflowNodeData } from '../types';

export default function ConditionalNode({ data, selected }: NodeProps) {
  const d = data as unknown as WorkflowNodeData;
  const condition = d.params?.condition;

  return (
    <div
      className={`
        min-w-[200px] rounded-xl border-2 px-4 py-3
        bg-amber-950/70
        transition-all duration-150
        ${selected
          ? 'border-amber-400 shadow-xl shadow-amber-500/25'
          : 'border-amber-700/60 hover:border-amber-600/80'
        }
      `}
    >
      {/* Target handle — top center */}
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-amber-500 !border-2 !border-amber-300 !w-3 !h-3"
      />

      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-amber-400 text-base leading-none font-bold">◇</span>
        <span className="text-[10px] text-amber-400 uppercase tracking-widest font-bold">Condition</span>
      </div>

      {/* Label */}
      <p className="text-sm font-semibold text-white leading-tight">{d.label}</p>

      {/* Method */}
      <p className="text-[11px] text-amber-300/50 font-mono mt-1 truncate">{d.method}()</p>

      {/* Condition expression preview */}
      {condition && (
        <div className="mt-2 pt-2 border-t border-amber-800/40">
          <code className="text-[10px] text-amber-300/70 font-mono break-all">{condition}</code>
        </div>
      )}

      {/* True / False labels above handles */}
      <div className="flex justify-between mt-3 px-1">
        <span className="text-[10px] font-bold text-emerald-400">✓ True</span>
        <span className="text-[10px] font-bold text-red-400">✗ False</span>
      </div>

      {/* Two source handles: True (left) and False (right) */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="true"
        className="!bg-emerald-500 !border-2 !border-emerald-300 !w-3 !h-3"
        style={{ left: '28%' }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="false"
        className="!bg-red-500 !border-2 !border-red-300 !w-3 !h-3"
        style={{ left: '72%' }}
      />
    </div>
  );
}
