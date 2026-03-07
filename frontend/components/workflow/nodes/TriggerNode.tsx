'use client';

import { Handle, Position, type NodeProps } from '@xyflow/react';
import { type WorkflowNodeData } from '../types';

export default function TriggerNode({ data, selected }: NodeProps) {
  const d = data as unknown as WorkflowNodeData;

  return (
    <div
      className={`
        min-w-[192px] rounded-xl border-2 px-4 py-3
        bg-blue-950/70
        transition-all duration-150
        ${selected
          ? 'border-blue-400 shadow-xl shadow-blue-500/25'
          : 'border-blue-700/60 hover:border-blue-600/80'
        }
      `}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-blue-400 text-base leading-none">⚡</span>
        <span className="text-[10px] text-blue-400 uppercase tracking-widest font-bold">Trigger</span>
      </div>

      {/* Label */}
      <p className="text-sm font-semibold text-white leading-tight">{d.label}</p>

      {/* Node type */}
      <p className="text-[11px] text-blue-300/50 font-mono mt-1 truncate">{d.nodeType}</p>

      {/* Source handle — bottom center */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-blue-500 !border-2 !border-blue-300 !w-3 !h-3"
      />
    </div>
  );
}
