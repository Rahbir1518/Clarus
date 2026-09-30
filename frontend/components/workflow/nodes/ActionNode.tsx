'use client';

import { Handle, Position, type NodeProps } from '@xyflow/react';
import { type WorkflowNodeData } from '../types';

export default function ActionNode({ data, selected }: NodeProps) {
  const d = data as unknown as WorkflowNodeData;
  const paramKeys = Object.keys(d.params ?? {});

  return (
    <div
      className={`
        min-w-[220px] rounded-xl border-2 px-4 py-3
        bg-card
        transition-all duration-150
        ${selected
          ? 'border-purple-500 shadow-lg shadow-purple-100'
          : 'border-purple-200 hover:border-purple-300'
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
        <span className="size-2 rounded-full bg-purple-500" />
        <span className="text-xs text-purple-600 uppercase tracking-widest font-bold">Action</span>
      </div>

      {/* Label */}
      <p className="text-sm font-semibold text-foreground leading-tight">{d.label}</p>

      {/* Node type */}
      <p className="text-[13px] text-purple-400 font-mono mt-1 truncate">{d.nodeType}</p>

      {/* Param preview */}
      {paramKeys.length > 0 && (
        <div className="mt-2 pt-2 border-t border-purple-200 space-y-0.5">
          {paramKeys.slice(0, 2).map((key) => (
            <div key={key} className="flex items-center gap-1.5 text-xs font-mono text-purple-400">
              <span className="text-purple-300">→</span>
              <span className="truncate">{key}</span>
            </div>
          ))}
          {paramKeys.length > 2 && (
            <p className="text-xs text-purple-300 pl-3.5">+{paramKeys.length - 2} more</p>
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
