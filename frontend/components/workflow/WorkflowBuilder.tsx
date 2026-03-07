'use client';

import '@xyflow/react/dist/style.css';

import { useState, useCallback, useRef, useEffect, type DragEvent } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAuth0 } from '@auth0/auth0-react';
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
import {
  createWorkflow,
  updateWorkflow,
  listWorkflows,
  getWorkflow,
  executeWorkflow,
  listPatients,
  createPatient,
} from '@/services/api';

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
  const { user } = useAuth0();
  const searchParams = useSearchParams();

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);

  // ── Save-to-DB state ──────────────────────────────────────────────────
  const [savedWorkflowId, setSavedWorkflowId] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [showNameModal, setShowNameModal] = useState(false);
  const [workflowName, setWorkflowName] = useState('');
  const [workflowDescription, setWorkflowDescription] = useState('');

  // ── Load Workflow modal state ─────────────────────────────────────────
  const [showLoadModal, setShowLoadModal] = useState(false);
  const [availableWorkflows, setAvailableWorkflows] = useState<any[]>([]);
  const [loadingWorkflows, setLoadingWorkflows] = useState(false);
  const [loadWorkflowError, setLoadWorkflowError] = useState<string | null>(null);

  // ── Run Workflow modal state ──────────────────────────────────────────
  const [showRunModal, setShowRunModal] = useState(false);
  const [patients, setPatients] = useState<any[]>([]);
  const [loadingPatients, setLoadingPatients] = useState(false);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle');
  const [runResult, setRunResult] = useState<any | null>(null);
  const [showAddPatient, setShowAddPatient] = useState(false);
  const [newPatientName, setNewPatientName] = useState('');
  const [newPatientPhone, setNewPatientPhone] = useState('');
  const [addingPatient, setAddingPatient] = useState(false);

  // ── Auto-load workflow from URL query param ─────────────────────────
  useEffect(() => {
    const workflowId = searchParams.get('id');
    if (!workflowId) return;
    (async () => {
      try {
        const wf = await getWorkflow(workflowId);
        if (wf && wf.id) {
          const loadedNodes: Node[] = Array.isArray(wf.nodes) ? wf.nodes : [];
          const loadedEdges: Edge[] = Array.isArray(wf.edges) ? wf.edges : [];
          setNodes(loadedNodes);
          setEdges(loadedEdges);
          setSavedWorkflowId(wf.id);
          setWorkflowName(wf.name ?? '');
          setWorkflowDescription(wf.description ?? '');
          setTimeout(() => fitView({ padding: 0.15, duration: 400 }), 100);
        }
      } catch {
        // silently fail — user can load manually
      }
    })();
  }, [searchParams, setNodes, setEdges, fitView]);

  // ── Connections ───────────────────────────────────────────────────────

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

  // ── Selection ─────────────────────────────────────────────────────────

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode(node);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  // ── Drag and drop from palette ────────────────────────────────────────

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

  // ── Properties panel updates ──────────────────────────────────────────

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

  // ── Toolbar actions ───────────────────────────────────────────────────

  const clearCanvas = useCallback(() => {
    setNodes([]);
    setEdges([]);
    setSelectedNode(null);
    setSavedWorkflowId(null);
    setWorkflowName('');
    setWorkflowDescription('');
  }, [setNodes, setEdges]);

  const loadExample = useCallback(() => {
    setNodes(EXAMPLE_NODES);
    setEdges(EXAMPLE_EDGES);
    setSelectedNode(null);
    setTimeout(() => fitView({ padding: 0.15, duration: 400 }), 50);
  }, [setNodes, setEdges, fitView]);

  const exportWorkflow = useCallback(() => {
    const workflow = { nodes, edges };
    const blob = new Blob([JSON.stringify(workflow, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `workflow-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [nodes, edges]);

  // ── Save to Supabase via backend API ──────────────────────────────────

  const handleSaveClick = useCallback(() => {
    if (savedWorkflowId) {
      doSave(workflowName, workflowDescription);
    } else {
      setShowNameModal(true);
    }
  }, [savedWorkflowId, workflowName, workflowDescription]);

  const doSave = useCallback(async (name: string, description: string) => {
    setSaveStatus('saving');
    setShowNameModal(false);
    setWorkflowName(name);
    setWorkflowDescription(description);

    const doctorId = user?.sub ?? 'anonymous';

    try {
      if (savedWorkflowId) {
        await updateWorkflow(savedWorkflowId, {
          name,
          description,
          nodes: nodes as unknown[],
          edges: edges as unknown[],
        });
      } else {
        const result = await createWorkflow({
          doctor_id: doctorId,
          name,
          description,
          nodes: nodes as unknown[],
          edges: edges as unknown[],
        });
        setSavedWorkflowId(result.id);
      }
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus('idle'), 2500);
    } catch {
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 3000);
    }
  }, [savedWorkflowId, nodes, edges, user]);

  // ── Load Workflow ─────────────────────────────────────────────────────

  const openLoadModal = useCallback(async () => {
    setShowLoadModal(true);
    setLoadingWorkflows(true);
    setLoadWorkflowError(null);
    try {
      // Fetch all workflows — no doctor_id filter so we always get results
      // regardless of auth state or id format differences
      const workflows = await listWorkflows();
      setAvailableWorkflows(Array.isArray(workflows) ? workflows : []);
    } catch (err: any) {
      setAvailableWorkflows([]);
      setLoadWorkflowError(err?.message ?? 'Failed to load workflows. Is the backend running?');
    } finally {
      setLoadingWorkflows(false);
    }
  }, []);

  const loadWorkflow = useCallback((wf: any) => {
    const loadedNodes: Node[] = Array.isArray(wf.nodes) ? wf.nodes : [];
    const loadedEdges: Edge[] = Array.isArray(wf.edges) ? wf.edges : [];
    setNodes(loadedNodes);
    setEdges(loadedEdges);
    setSavedWorkflowId(wf.id);
    setWorkflowName(wf.name ?? '');
    setWorkflowDescription(wf.description ?? '');
    setSelectedNode(null);
    setShowLoadModal(false);
    setTimeout(() => fitView({ padding: 0.15, duration: 400 }), 50);
  }, [setNodes, setEdges, fitView]);

  // ── Run Workflow ──────────────────────────────────────────────────────

  const openRunModal = useCallback(async () => {
    if (!savedWorkflowId) return;
    setShowRunModal(true);
    setRunStatus('idle');
    setRunResult(null);
    setSelectedPatientId(null);
    setShowAddPatient(false);
    setNewPatientName('');
    setNewPatientPhone('');
    setLoadingPatients(true);
    try {
      const doctorId = user?.sub ?? undefined;
      const data = await listPatients(doctorId);
      setPatients(Array.isArray(data) ? data : []);
    } catch {
      setPatients([]);
    } finally {
      setLoadingPatients(false);
    }
  }, [savedWorkflowId, user]);

  const handleAddPatient = useCallback(async () => {
    if (!newPatientName.trim() || !newPatientPhone.trim()) return;
    setAddingPatient(true);
    try {
      const doctorId = user?.sub ?? 'anonymous';
      const created = await createPatient({
        name: newPatientName.trim(),
        phone: newPatientPhone.trim(),
        doctor_id: doctorId,
      });
      setPatients((prev) => [created, ...prev]);
      setSelectedPatientId(created.id);
      setShowAddPatient(false);
      setNewPatientName('');
      setNewPatientPhone('');
    } catch {
      // ignore — patient still won't show
    } finally {
      setAddingPatient(false);
    }
  }, [newPatientName, newPatientPhone, user]);

  const handleRun = useCallback(async () => {
    if (!savedWorkflowId || !selectedPatientId) return;
    setRunStatus('running');
    setRunResult(null);
    try {
      const result = await executeWorkflow(savedWorkflowId, selectedPatientId);
      setRunResult(result);
      setRunStatus(result.status === 'failed' ? 'error' : 'success');
    } catch {
      setRunStatus('error');
      setRunResult({ execution_log: [], status: 'failed', call_log_id: null });
    }
  }, [savedWorkflowId, selectedPatientId]);

  // ── Helpers ───────────────────────────────────────────────────────────

  const formatDate = (iso: string) => {
    try { return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }); }
    catch { return iso; }
  };

  const stepColor = (s: string) => {
    if (s === 'ok') return '#10b981';
    if (s === 'error') return '#ef4444';
    return '#6b7280';
  };

  // ────────────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-white">

      {/* ── Toolbar ──────────────────────────────────────────────────────── */}
      <header className="h-12 shrink-0 flex items-center justify-between px-4 border-b border-gray-800 bg-gray-900">
        <div className="flex items-center gap-2">
          <a href="/dashboard" className="text-indigo-400 font-bold text-sm tracking-widest hover:text-indigo-300 transition-colors">CLARUS</a>
          <span className="text-gray-700 text-sm">/</span>
          <span className="text-gray-400 text-sm">
            {workflowName ? workflowName : 'Workflow Builder'}
          </span>

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
            onClick={openLoadModal}
            className="px-3 py-1 text-xs rounded border border-gray-700 text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
          >
            Load Workflow
          </button>
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
            onClick={exportWorkflow}
            disabled={nodes.length === 0}
            className="px-3 py-1 text-xs rounded border border-gray-700 text-gray-400 hover:bg-gray-800 hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Export JSON
          </button>
          <button
            onClick={handleSaveClick}
            disabled={nodes.length === 0 || saveStatus === 'saving'}
            className={`px-3 py-1 text-xs rounded text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
              saveStatus === 'saved'
                ? 'bg-emerald-600'
                : saveStatus === 'error'
                  ? 'bg-red-600'
                  : 'bg-indigo-600 hover:bg-indigo-500'
            }`}
          >
            {saveStatus === 'saving'
              ? 'Saving…'
              : saveStatus === 'saved'
                ? '✓ Saved'
                : saveStatus === 'error'
                  ? '✕ Error'
                  : savedWorkflowId
                    ? 'Update Workflow'
                    : 'Save Workflow'}
          </button>
          <button
            onClick={openRunModal}
            disabled={!savedWorkflowId}
            title={!savedWorkflowId ? 'Save the workflow first' : 'Run this workflow'}
            className="px-3 py-1 text-xs rounded bg-emerald-700 hover:bg-emerald-600 text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
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
                    Load Workflow
                  </span>{' '}
                  to reload a saved workflow, or{' '}
                  <span className="text-gray-500 bg-gray-800/60 px-1.5 py-0.5 rounded font-mono">
                    Load Example
                  </span>{' '}
                  to see a pre-built one
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

      {/* ── Save workflow name modal ───────────────────────────────────── */}
      {showNameModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md shadow-2xl">
            <h2 className="text-lg font-semibold text-white mb-4">Save Workflow</h2>
            <label className="block text-sm text-gray-400 mb-1">Name *</label>
            <input
              autoFocus
              type="text"
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              placeholder="e.g. Lab Results Follow-Up"
              className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 mb-3"
            />
            <label className="block text-sm text-gray-400 mb-1">Description</label>
            <textarea
              value={workflowDescription}
              onChange={(e) => setWorkflowDescription(e.target.value)}
              placeholder="Optional description…"
              rows={2}
              className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 mb-4 resize-none"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowNameModal(false)}
                className="px-4 py-2 text-xs rounded-lg border border-gray-700 text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                disabled={!workflowName.trim()}
                onClick={() => doSave(workflowName.trim(), workflowDescription.trim())}
                className="px-4 py-2 text-xs rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Load Workflow modal ────────────────────────────────────────── */}
      {showLoadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Load Workflow</h2>
              <button
                onClick={() => setShowLoadModal(false)}
                className="text-gray-500 hover:text-white text-xl leading-none"
              >×</button>
            </div>

            {loadingWorkflows ? (
              <p className="text-sm text-gray-400 text-center py-8">Loading workflows…</p>
            ) : loadWorkflowError ? (
              <p className="text-sm text-red-400 text-center py-8">{loadWorkflowError}</p>
            ) : availableWorkflows.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-8">No saved workflows found.</p>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                {availableWorkflows.map((wf) => (
                  <button
                    key={wf.id}
                    onClick={() => loadWorkflow(wf)}
                    className="w-full text-left rounded-lg border border-gray-700 bg-gray-800 hover:bg-gray-750 hover:border-indigo-500 px-4 py-3 transition-colors group"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-white group-hover:text-indigo-300 truncate">{wf.name}</p>
                        {wf.description && (
                          <p className="text-xs text-gray-400 mt-0.5 truncate">{wf.description}</p>
                        )}
                        <div className="flex items-center gap-3 mt-1.5">
                          <span className="text-[10px] text-gray-500">
                            {Array.isArray(wf.nodes) ? wf.nodes.length : 0} nodes
                          </span>
                          <span className="text-[10px] text-gray-500">
                            {Array.isArray(wf.edges) ? wf.edges.length : 0} edges
                          </span>
                          <span className="text-[10px] text-gray-500">
                            {formatDate(wf.created_at)}
                          </span>
                        </div>
                      </div>
                      <span className={`flex-shrink-0 text-[10px] px-2 py-0.5 rounded-full font-medium ${
                        wf.status === 'ENABLED'
                          ? 'bg-emerald-900/50 text-emerald-400'
                          : 'bg-gray-700 text-gray-400'
                      }`}>
                        {wf.status}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Run Workflow modal ─────────────────────────────────────────── */}
      {showRunModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-lg font-semibold text-white">Run Workflow</h2>
              <button
                onClick={() => { setShowRunModal(false); setRunResult(null); setRunStatus('idle'); }}
                className="text-gray-500 hover:text-white text-xl leading-none"
              >×</button>
            </div>
            <p className="text-xs text-gray-400 mb-4">
              Workflow: <span className="text-indigo-300 font-medium">{workflowName}</span>
            </p>

            {/* Patient picker */}
            {runStatus === 'idle' && (
              <>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm text-gray-400 font-medium">Select Patient</label>
                  <button
                    onClick={() => setShowAddPatient((v) => !v)}
                    className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                  >
                    {showAddPatient ? '− Cancel' : '+ Add Patient'}
                  </button>
                </div>

                {showAddPatient && (
                  <div className="mb-3 rounded-lg border border-gray-700 bg-gray-800 p-3 space-y-2">
                    <input
                      type="text"
                      value={newPatientName}
                      onChange={(e) => setNewPatientName(e.target.value)}
                      placeholder="Full Name"
                      className="w-full px-3 py-1.5 rounded-lg bg-gray-900 border border-gray-700 text-white text-xs placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                    <input
                      type="tel"
                      value={newPatientPhone}
                      onChange={(e) => setNewPatientPhone(e.target.value)}
                      placeholder="Phone (e.g. +1 555 000 0000)"
                      className="w-full px-3 py-1.5 rounded-lg bg-gray-900 border border-gray-700 text-white text-xs placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                    <button
                      onClick={handleAddPatient}
                      disabled={addingPatient || !newPatientName.trim() || !newPatientPhone.trim()}
                      className="px-3 py-1 text-xs rounded bg-indigo-600 hover:bg-indigo-500 text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      {addingPatient ? 'Saving…' : 'Create Patient'}
                    </button>
                  </div>
                )}

                {loadingPatients ? (
                  <p className="text-xs text-gray-500 mb-4">Loading patients…</p>
                ) : patients.length === 0 && !showAddPatient ? (
                  <p className="text-xs text-gray-500 mb-4">No patients yet — add one above.</p>
                ) : (
                  <div className="space-y-1.5 max-h-48 overflow-y-auto mb-4 pr-1">
                    {patients.map((p) => (
                      <button
                        key={p.id}
                        onClick={() => setSelectedPatientId(p.id)}
                        className={`w-full text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                          selectedPatientId === p.id
                            ? 'border-indigo-500 bg-indigo-900/30 text-white'
                            : 'border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-600'
                        }`}
                      >
                        <span className="font-medium">{p.name}</span>
                        <span className="text-xs text-gray-500 ml-2">{p.phone}</span>
                      </button>
                    ))}
                  </div>
                )}

                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => { setShowRunModal(false); }}
                    className="px-4 py-2 text-xs rounded-lg border border-gray-700 text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    disabled={!selectedPatientId}
                    onClick={handleRun}
                    className="px-4 py-2 text-xs rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    ▶ Execute
                  </button>
                </div>
              </>
            )}

            {/* Running state */}
            {runStatus === 'running' && (
              <div className="flex flex-col items-center justify-center py-10 gap-3">
                <svg className="animate-spin size-8 text-emerald-400" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                <p className="text-sm text-gray-400">Executing workflow…</p>
              </div>
            )}

            {/* Result state */}
            {(runStatus === 'success' || runStatus === 'error') && runResult && (
              <>
                <div className={`flex items-center gap-2 mb-4 rounded-lg px-3 py-2 ${
                  runStatus === 'success' ? 'bg-emerald-900/30 border border-emerald-700' : 'bg-red-900/30 border border-red-700'
                }`}>
                  <span className="text-sm font-semibold">
                    {runStatus === 'success' ? '✓ Completed' : '✕ Failed'}
                  </span>
                  {runResult.call_log_id && (
                    <span className="text-[10px] text-gray-400 ml-auto">
                      Log&nbsp;ID:&nbsp;{runResult.call_log_id.slice(0, 8)}…
                    </span>
                  )}
                </div>

                <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1 mb-4">
                  {(runResult.execution_log ?? []).map((step: any, i: number) => (
                    <div key={i} className="rounded-lg bg-gray-800 border border-gray-700 px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span
                          className="size-2 rounded-full flex-shrink-0"
                          style={{ backgroundColor: stepColor(step.status) }}
                        />
                        <span className="text-xs font-medium text-white">{step.label || step.node_type}</span>
                        <span className="ml-auto text-[10px] text-gray-500 capitalize">{step.status}</span>
                      </div>
                      <p className="text-[11px] text-gray-400 mt-0.5 pl-4">{step.message}</p>
                    </div>
                  ))}
                </div>

                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => { setRunStatus('idle'); setRunResult(null); setSelectedPatientId(null); }}
                    className="px-4 py-2 text-xs rounded-lg border border-gray-700 text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
                  >
                    Run Again
                  </button>
                  <button
                    onClick={() => { setShowRunModal(false); setRunResult(null); setRunStatus('idle'); }}
                    className="px-4 py-2 text-xs rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
                  >
                    Close
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
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
