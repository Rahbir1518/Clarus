'use client';

import { useState, useCallback, useRef } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { type WorkflowNodeData } from '../types';
import { useCmdHover } from '../CmdHoverContext';

export default function ConditionalNode({ data, selected }: NodeProps) {
  const d = data as unknown as WorkflowNodeData;
  const condition = d.params?.condition;
  const { cmdHeld, setHandle } = useCmdHover();
  const [hoverSide, setHoverSide] = useState<'left' | 'right' | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const onMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!cmdHeld || !rootRef.current) {
        if (hoverSide) setHoverSide(null);
        return;
      }
      const rect = rootRef.current.getBoundingClientRect();
      const midX = rect.left + rect.width / 2;
      const side = e.clientX < midX ? 'left' : 'right';
      setHoverSide(side);
      setHandle(side === 'left' ? 'true' : 'false');
    },
    [cmdHeld, hoverSide, setHandle]
  );

  const onMouseLeave = useCallback(() => {
    setHoverSide(null);
  }, []);

  return (
    <div
      ref={rootRef}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
      className={`
        min-w-[200px] rounded-xl border-2 px-4 py-3
        bg-card relative overflow-hidden
        transition-all duration-150
        ${selected
          ? 'border-amber-500 shadow-lg shadow-amber-100'
          : 'border-amber-200 hover:border-amber-300'
        }
      `}
    >
      {/* Cmd+hover overlays */}
      <div
        className="absolute inset-y-0 left-0 w-1/2 rounded-l-xl transition-all duration-150 pointer-events-none"
        style={{
          backgroundColor: cmdHeld && hoverSide === 'left' ? 'rgba(16,185,129,0.12)' : 'transparent',
        }}
      />
      <div
        className="absolute inset-y-0 right-0 w-1/2 rounded-r-xl transition-all duration-150 pointer-events-none"
        style={{
          backgroundColor: cmdHeld && hoverSide === 'right' ? 'rgba(239,68,68,0.12)' : 'transparent',
        }}
      />

      {/* Target handle — top center */}
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-amber-500 !border-2 !border-amber-300 !w-3 !h-3"
      />

      {/* Header */}
      <div className="relative flex items-center gap-2 mb-2">
        <span className="text-amber-600 text-base leading-none font-bold">◇</span>
        <span className="text-[10px] text-amber-600 uppercase tracking-widest font-bold">Condition</span>
      </div>

      {/* Label */}
      <p className="relative text-sm font-semibold text-foreground leading-tight">{d.label}</p>

      {/* Node type */}
      <p className="relative text-[11px] text-amber-400 font-mono mt-1 truncate">{d.nodeType}</p>

      {/* Condition expression preview */}
      {condition && (
        <div className="relative mt-2 pt-2 border-t border-amber-200">
          <code className="text-[10px] text-amber-500 font-mono break-all">{condition}</code>
        </div>
      )}

      {/* True / False labels above handles */}
      <div className="relative flex justify-between mt-3 px-1">
        <span className="text-[10px] font-bold text-emerald-600">✓ True</span>
        <span className="text-[10px] font-bold text-red-500">✗ False</span>
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
