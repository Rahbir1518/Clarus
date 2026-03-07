'use client';

import '@xyflow/react/dist/style.css';

import { useState, useCallback, type DragEvent } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  addEdge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type Connection,
  type NodeTypes,
  BackgroundVariant,
} from '@xyflow/react';

import { NodePalette } from './NodePalette';
import { PropertiesPanel } from './PropertiesPanel';
import TriggerNode from './nodes/TriggerNode';
import ActionNode from './nodes/ActionNode';
import ConditionalNode from './nodes/ConditionalNode';
import EndpointNode from './nodes/EndpointNode';
import { type CatalogueNode } from './types';

// ─── Register custom node types ─────────────────────────────────────────────

const nodeTypes: NodeTypes = {
  trigger: TriggerNode,
  action: ActionNode,
  conditional: ConditionalNode,
  endpoint: EndpointNode,
};

// ─── Edge defaults ───────────────────────────────────────────────────────────

const defaultEdgeOptions = {
  animated: true,
  style: { stroke: '#6366f1', strokeWidth: 2 },
};

// ─── Node ID generator ───────────────────────────────────────────────────────

let _idCounter = 0;
const newId = () => `node_${Date.now()}_${++_idCounter}`;

// ─── Example workflow ────────────────────────────────────────────────────────

const EXAMPLE_NODES: Node[] = [
  {
    id: 'ex_1',
    type: 'trigger',
    position: { x: 280, y: 40 },
    data: { label: 'Lab Results Received', nodeType: 'lab_results_received', description: 'Lab result arrives for patient', params: {} },
  },
  {
    id: 'ex_2',
    type: 'conditional',
    position: { x: 280, y: 180 },
    data: { label: 'Check Result Values', nodeType: 'check_result_values', description: 'Are results abnormal?', params: { result: '' } },
  },
  {
    id: 'ex_3',
    type: 'action',
    position: { x: 100, y: 340 },
    data: { label: 'Call Patient', nodeType: 'call_patient', description: 'Place outbound Twilio call', params: { message: '' } },
  },
  {
    id: 'ex_4',
    type: 'action',
    position: { x: 100, y: 490 },
    data: { label: 'Schedule Appointment', nodeType: 'schedule_appointment', description: 'Schedule follow-up', params: {} },
  },
  {
    id: 'ex_5',
    type: 'endpoint',
    position: { x: 100, y: 640 },
    data: { label: 'Send Summary to Doctor', nodeType: 'send_summary_to_doctor', description: 'Notify the doctor', params: {} },
  },
  {
    id: 'ex_6',
    type: 'action',
    position: { x: 460, y: 340 },
    data: { label: 'Send SMS', nodeType: 'send_sms', description: 'SMS with normal results', params: { message: 'Your results are normal.' } },
  },
  {
    id: 'ex_7',
    type: 'endpoint',
    position: { x: 460, y: 490 },
    data: { label: 'Log Completion', nodeType: 'log_completion', description: 'Workflow complete', params: {} },
  },
];

const EXAMPLE_EDGES: Edge[] = [
  { id: 'ee_1', source: 'ex_1', target: 'ex_2', animated: true, style: { stroke: '#6366f1', strokeWidth: 2 } },
  { id: 'ee_2', source: 'ex_2', sourceHandle: 'true', target: 'ex_3', animated: true, style: { stroke: '#10b981', strokeWidth: 2 } },
  { id: 'ee_3', source: 'ex_2', sourceHandle: 'false', target: 'ex_6', animated: true, style: { stroke: '#ef4444', strokeWidth: 2 } },
  { id: 'ee_4', source: 'ex_3', target: 'ex_4', animated: true, style: { stroke: '#6366f1', strokeWidth: 2 } },
  { id: 'ee_5', source: 'ex_4', target: 'ex_5', animated: true, style: { stroke: '#6366f1', strokeWidth: 2 } },
  { id: 'ee_6', source: 'ex_6', target: 'ex_7', animated: true, style: { stroke: '#6366f1', strokeWidth: 2 } },
];

// ─── Inner component — uses useReactFlow, must be inside ReactFlowProvider ──

function FlowContent() {
  const { screenToFlowPosition, fitView } = useReactFlow();

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);

  // ── Connections ──────────────────────────────────────────────────────────

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) =>
        addEdge(
          { ...connection, animated: true, style: { stroke: '#6366f1', strokeWidth: 2 } },
          eds
        )
      );
    },
    [setEdges]
  );

  // ── Selection ────────────────────────────────────────────────────────────

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode(node);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  // ── Drag and drop from palette ───────────────────────────────────────────

  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();

      const raw = event.dataTransfer.getData('application/reactflow');
      if (!raw) return;

      const dropped = JSON.parse(raw) as CatalogueNode & { reactFlowType: string };
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });

      const newNode: Node = {
        id: newId(),
        type: dropped.reactFlowType,
        position,
        data: {
          label: dropped.label,
          nodeType: dropped.nodeType,
          description: dropped.description,
          params: { ...dropped.params },
        },
      };

      setNodes((nds) => nds.concat(newNode));
    },
    [screenToFlowPosition, setNodes]
  );

  // ── Properties panel updates ─────────────────────────────────────────────

  const updateNodeParams = useCallback(
    (nodeId: string, params: Record<string, string>) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId ? { ...n, data: { ...n.data, params } } : n
        )
      );
      setSelectedNode((prev) =>
        prev?.id === nodeId ? { ...prev, data: { ...prev.data, params } } : prev
      );
    },
    [setNodes]
  );

  const deleteNode = useCallback(
    (nodeId: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== nodeId));
      setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
      setSelectedNode((prev) => (prev?.id === nodeId ? null : prev));
    },
    [setNodes, setEdges]
  );

  // ── Toolbar actions ──────────────────────────────────────────────────────

  const clearCanvas = useCallback(() => {
    setNodes([]);
    setEdges([]);
    setSelectedNode(null);
  }, [setNodes, setEdges]);

  const loadExample = useCallback(() => {
    setNodes(EXAMPLE_NODES);
    setEdges(EXAMPLE_EDGES);
    setSelectedNode(null);
    setTimeout(() => fitView({ padding: 0.15, duration: 400 }), 50);
  }, [setNodes, setEdges, fitView]);

  const saveWorkflow = useCallback(() => {
    const workflow = { nodes, edges };
    const blob = new Blob([JSON.stringify(workflow, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `workflow-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [nodes, edges]);

  // ────────────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-white">

      {/* ── Toolbar ──────────────────────────────────────────────────────── */}
      <header className="h-12 shrink-0 flex items-center justify-between px-4 border-b border-gray-800 bg-gray-900">
        <div className="flex items-center gap-2">
          <span className="text-indigo-400 font-bold text-sm tracking-widest">CLARUS</span>
          <span className="text-gray-700 text-sm">/</span>
          <span className="text-gray-400 text-sm">Workflow Builder</span>

          {/* Node / edge counters */}
          {(nodes.length > 0 || edges.length > 0) && (
            <div className="flex items-center gap-1.5 ml-2">
              <span className="text-[10px] bg-gray-800 border border-gray-700 text-gray-400 px-2 py-0.5 rounded-full">
                {nodes.length} nodes
              </span>
              <span className="text-[10px] bg-gray-800 border border-gray-700 text-gray-400 px-2 py-0.5 rounded-full">
                {edges.length} edges
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadExample}
            className="px-3 py-1 text-xs rounded border border-gray-700 text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
          >
            Load Example
          </button>
          <button
            onClick={clearCanvas}
            disabled={nodes.length === 0}
            className="px-3 py-1 text-xs rounded border border-gray-700 text-gray-400 hover:bg-gray-800 hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Clear
          </button>
          <button
            onClick={saveWorkflow}
            disabled={nodes.length === 0}
            className="px-3 py-1 text-xs rounded bg-indigo-600 hover:bg-indigo-500 text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Export JSON
          </button>
          <button className="px-3 py-1 text-xs rounded bg-emerald-700 hover:bg-emerald-600 text-white transition-colors">
            ▶&nbsp;Run
          </button>
        </div>
      </header>

      {/* ── Body ─────────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left: Node palette */}
        <NodePalette />

        {/* Centre: React Flow canvas */}
        <div
          className="flex-1 relative"
          onDrop={onDrop}
          onDragOver={onDragOver}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            defaultEdgeOptions={defaultEdgeOptions}
            colorMode="dark"
            fitView
            proOptions={{ hideAttribution: true }}
            deleteKeyCode="Delete"
          >
            <Background
              variant={BackgroundVariant.Dots}
              color="#1f2937"
              gap={20}
              size={1.5}
            />
            <Controls />
            <MiniMap
              nodeColor={(node) => {
                switch (node.type) {
                  case 'trigger': return '#3b82f6';
                  case 'action': return '#8b5cf6';
                  case 'conditional': return '#f59e0b';
                  case 'endpoint': return '#10b981';
                  default: return '#6b7280';
                }
              }}
              maskColor="rgba(0,0,0,0.7)"
            />
          </ReactFlow>

          {/* Empty-state hint */}
          {nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center space-y-2">
                <p className="text-gray-600 text-sm">
                  Drag nodes from the palette, or
                </p>
                <p className="text-gray-700 text-xs">
                  click{' '}
                  <span className="text-gray-500 bg-gray-800/60 px-1.5 py-0.5 rounded font-mono">
                    Load Example
                  </span>{' '}
                  to see a pre-built workflow
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Right: Properties panel */}
        <PropertiesPanel
          selectedNode={selectedNode}
          onUpdateParams={updateNodeParams}
          onDeleteNode={deleteNode}
        />
      </div>
    </div>
  );
}

// ─── Public export — wraps inner component in provider ──────────────────────

export default function WorkflowBuilder() {
  return (
    <ReactFlowProvider>
      <FlowContent />
    </ReactFlowProvider>
  );
}
