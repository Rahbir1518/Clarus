'use client';

import { Handle, Position, type NodeProps } from '@xyflow/react';
import { type WorkflowNodeData } from '../types';

export default function ActionNode({ data, selected }: NodeProps) {
  const d = data as unknown as WorkflowNodeData;
  const paramKeys = Object.keys(d.params ?? {});

  return (
    <div
      className={`
        min-w-[192px] rounded-xl border-2 px-4 py-3
        bg-purple-950/70
        transition-all duration-150
        ${selected
          ? 'border-purple-400 shadow-xl shadow-purple-500/25'
          : 'border-purple-700/60 hover:border-purple-600/80'
        }
      `}
    >
      {/* Target handle — top center */}
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-purple-500 !border-2 !border-purple-300 !w-3 !h-3"
      />

      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-purple-400 text-base leading-none">⚙</span>
        <span className="text-[10px] text-purple-400 uppercase tracking-widest font-bold">Action</span>
      </div>

      {/* Label */}
      <p className="text-sm font-semibold text-white leading-tight">{d.label}</p>

      {/* Method */}
      <p className="text-[11px] text-purple-300/50 font-mono mt-1 truncate">{d.method}()</p>

      {/* Param preview */}
      {paramKeys.length > 0 && (
        <div className="mt-2 pt-2 border-t border-purple-800/40 space-y-0.5">
          {paramKeys.slice(0, 2).map((key) => (
            <div key={key} className="flex items-center gap-1.5 text-[10px] font-mono text-purple-400/60">
              <span className="text-purple-700">→</span>
              <span className="truncate">{key}</span>
            </div>
          ))}
          {paramKeys.length > 2 && (
            <p className="text-[10px] text-purple-700 pl-3.5">+{paramKeys.length - 2} more</p>
          )}
        </div>
      )}

      {/* Source handle — bottom center */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-purple-500 !border-2 !border-purple-300 !w-3 !h-3"
      />
    </div>
  );
}
