'use client';

import { type Node } from '@xyflow/react';
import { CATEGORY_STYLES, type WorkflowNodeData } from './types';

const NODE_TYPE_CATEGORY: Record<string, keyof typeof CATEGORY_STYLES> = {
  trigger: 'Triggers',
  action: 'Actions',
  conditional: 'Conditionals',
  endpoint: 'Output',
};

interface Props {
  selectedNode: Node | null;
  onUpdateParams: (nodeId: string, params: Record<string, string>) => void;
  onDeleteNode: (nodeId: string) => void;
}

export function PropertiesPanel({ selectedNode, onUpdateParams, onDeleteNode }: Props) {
  if (!selectedNode) {
    return (
      <aside className="w-64 shrink-0 border-l border-gray-800 bg-gray-900 flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 shrink-0">
          <p className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Properties</p>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center gap-2 p-6">
          <div className="w-8 h-8 rounded-lg border-2 border-dashed border-gray-700 flex items-center justify-center">
            <span className="text-gray-600 text-xs">↖</span>
          </div>
          <p className="text-[11px] text-gray-600 text-center leading-relaxed">
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

  return (
    <aside className="w-64 shrink-0 border-l border-gray-800 bg-gray-900 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800 shrink-0">
        <p className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Properties</p>
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
          <p className="text-[10px] text-gray-500 uppercase tracking-widest mb-1.5">Label</p>
          <p className="text-sm font-semibold text-white">{data.label}</p>
        </div>

        {/* Node Type */}
        <div>
          <p className="text-[10px] text-gray-500 uppercase tracking-widest mb-1.5">Node Type</p>
          <code className="block text-xs font-mono text-indigo-300 bg-gray-800 px-3 py-2 rounded-lg break-all">
            {data.nodeType}
          </code>
        </div>

        {/* Description */}
        {data.description ? (
          <div>
            <p className="text-[10px] text-gray-500 uppercase tracking-widest mb-1.5">Description</p>
            <p className="text-xs text-gray-400 leading-relaxed">{data.description}</p>
          </div>
        ) : null}

        {/* Parameters */}
        {Object.keys(params).length > 0 && (
          <div>
            <p className="text-[10px] text-gray-500 uppercase tracking-widest mb-2.5">Parameters</p>
            <div className="space-y-3">
              {Object.entries(params).map(([key, value]) => (
                <div key={key}>
                  <label className="block text-[10px] text-gray-500 font-mono mb-1">{key}</label>
                  <input
                    type="text"
                    value={value}
                    onChange={(e) => handleParamChange(key, e.target.value)}
                    className="
                      w-full text-xs bg-gray-800 border border-gray-700 rounded-lg
                      px-3 py-2 text-gray-200 font-mono
                      focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30
                      placeholder-gray-600 transition-colors
                    "
                    placeholder={`{{${key}}}`}
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Divider */}
        <div className="border-t border-gray-800" />

        {/* Node ID */}
        <div>
          <p className="text-[10px] text-gray-600 uppercase tracking-widest mb-1">Node ID</p>
          <code className="text-[10px] text-gray-700 font-mono break-all">{selectedNode.id}</code>
        </div>

        {/* Delete button */}
        <button
          onClick={() => onDeleteNode(selectedNode.id)}
          className="
            w-full px-3 py-2 rounded-lg border border-red-900/50 text-red-400
            text-xs font-medium
            hover:bg-red-950/50 hover:border-red-700/50
            transition-colors duration-150
          "
        >
          Delete Node
        </button>
      </div>
    </aside>
  );
}
