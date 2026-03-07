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
  SelectionMode,
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
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { ArrowUpRight, Undo2, Redo2, MousePointer2, Hand } from 'lucide-react';
import dagre from 'dagre';
import { CmdHoverContext } from './CmdHoverContext';

// ─── Auto-layout helper (dagre) ─────────────────────────────────────────────

function getLayoutedElements(nodes: Node[], edges: Edge[], direction = 'TB') {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 80 });

  nodes.forEach((node) => {
    g.setNode(node.id, { width: 200, height: 100 });
  });
  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target);
  });

  dagre.layout(g);

  const layoutedNodes = nodes.map((node) => {
    const pos = g.node(node.id);
    return { ...node, position: { x: pos.x - 100, y: pos.y - 50 } };
  });

  return { nodes: layoutedNodes, edges };
}

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
  style: { stroke: '#C43B3B', strokeWidth: 2 },
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
  { id: 'ee_1', source: 'ex_1', target: 'ex_2', animated: true, style: { stroke: '#C43B3B', strokeWidth: 2 } },
  { id: 'ee_2', source: 'ex_2', sourceHandle: 'true', target: 'ex_3', animated: true, style: { stroke: '#10b981', strokeWidth: 2 } },
  { id: 'ee_3', source: 'ex_2', sourceHandle: 'false', target: 'ex_6', animated: true, style: { stroke: '#ef4444', strokeWidth: 2 } },
  { id: 'ee_4', source: 'ex_3', target: 'ex_4', animated: true, style: { stroke: '#C43B3B', strokeWidth: 2 } },
  { id: 'ee_5', source: 'ex_4', target: 'ex_5', animated: true, style: { stroke: '#C43B3B', strokeWidth: 2 } },
  { id: 'ee_6', source: 'ex_6', target: 'ex_7', animated: true, style: { stroke: '#C43B3B', strokeWidth: 2 } },
];

// ─── Inner component — uses useReactFlow, must be inside ReactFlowProvider ──

function FlowContent() {
  const { screenToFlowPosition, fitView } = useReactFlow();
  const { user } = useAuth0();
  const searchParams = useSearchParams();

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [selectMode, setSelectMode] = useState(true);

  // ── Cmd+hover connection state ──────────────────────────────────────
  const [cmdHeld, setCmdHeld] = useState(false);
  const lastHoveredRef = useRef<string | null>(null);
  const cmdHandleRef = useRef<string | undefined>(undefined);
  const setHandle = useCallback((h: string | undefined) => { cmdHandleRef.current = h; }, []);

  // ── Undo / Redo history ──────────────────────────────────────────────
  const historyRef = useRef<{ nodes: Node[]; edges: Edge[] }[]>([]);
  const historyIndexRef = useRef(-1);
  const isUndoRedoRef = useRef(false);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

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
          { ...connection, animated: true, style: { stroke: '#C43B3B', strokeWidth: 2 } },
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

  // ── Cmd+hover to connect nodes ───────────────────────────────────────

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey) {
        setCmdHeld(true);
        lastHoveredRef.current = null;
      }
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (!e.metaKey && !e.ctrlKey) {
        setCmdHeld(false);
        lastHoveredRef.current = null;
        cmdHandleRef.current = undefined;
      }
    };
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
    };
  }, []);

  // ── Undo / Redo ─────────────────────────────────────────────────────

  const pushHistory = useCallback((n: Node[], e: Edge[]) => {
    const history = historyRef.current;
    const idx = historyIndexRef.current;
    // Trim any future entries if we branched
    historyRef.current = history.slice(0, idx + 1);
    historyRef.current.push({
      nodes: JSON.parse(JSON.stringify(n)),
      edges: JSON.parse(JSON.stringify(e)),
    });
    historyIndexRef.current = historyRef.current.length - 1;
    setCanUndo(historyIndexRef.current > 0);
    setCanRedo(false);
  }, []);

  // Debounced history recording — only structural changes (not position/selection moves)
  useEffect(() => {
    if (isUndoRedoRef.current) {
      isUndoRedoRef.current = false;
      return;
    }
    const timer = setTimeout(() => {
      const last = historyRef.current[historyIndexRef.current];
      const stripNode = (n: Node) => ({ id: n.id, type: n.type, data: n.data });
      const stripEdge = (e: Edge) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle, data: e.data });
      const nodesKey = JSON.stringify(nodes.map(stripNode));
      const edgesKey = JSON.stringify(edges.map(stripEdge));
      if (last) {
        const lastNodesKey = JSON.stringify(last.nodes.map(stripNode));
        const lastEdgesKey = JSON.stringify(last.edges.map(stripEdge));
        if (nodesKey === lastNodesKey && edgesKey === lastEdgesKey) return;
      }
      pushHistory(nodes, edges);
    }, 300);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges]);

  const undo = useCallback(() => {
    const idx = historyIndexRef.current;
    if (idx <= 0) return;
    const newIdx = idx - 1;
    historyIndexRef.current = newIdx;
    const snap = historyRef.current[newIdx];
    isUndoRedoRef.current = true;
    setNodes(JSON.parse(JSON.stringify(snap.nodes)));
    isUndoRedoRef.current = true;
    setEdges(JSON.parse(JSON.stringify(snap.edges)));
    setCanUndo(newIdx > 0);
    setCanRedo(true);
  }, [setNodes, setEdges]);

  const redo = useCallback(() => {
    const idx = historyIndexRef.current;
    if (idx >= historyRef.current.length - 1) return;
    const newIdx = idx + 1;
    historyIndexRef.current = newIdx;
    const snap = historyRef.current[newIdx];
    isUndoRedoRef.current = true;
    setNodes(JSON.parse(JSON.stringify(snap.nodes)));
    isUndoRedoRef.current = true;
    setEdges(JSON.parse(JSON.stringify(snap.edges)));
    setCanUndo(true);
    setCanRedo(newIdx < historyRef.current.length - 1);
  }, [setNodes, setEdges]);

  // Keyboard shortcuts for undo/redo + select/pan mode
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Skip if user is typing in an input/textarea
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;

      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        undo();
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && e.shiftKey) {
        e.preventDefault();
        redo();
      }
      if (e.key === 'v' && !e.metaKey && !e.ctrlKey) setSelectMode(true);
      if (e.key === 'h' && !e.metaKey && !e.ctrlKey) setSelectMode(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [undo, redo]);

  const onNodeMouseEnter = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (!cmdHeld) return;
      const prev = lastHoveredRef.current;
      if (prev && prev !== node.id) {
        // Detect sourceHandle for conditional nodes via ref set by ConditionalNode
        let sourceHandle: string | undefined;
        const prevNode = nodes.find((n) => n.id === prev);
        if (prevNode?.type === 'conditional') {
          sourceHandle = cmdHandleRef.current ?? 'true';
        }
        setEdges((eds) =>
          addEdge(
            {
              id: `e_${prev}_${node.id}_${Date.now()}`,
              source: prev,
              target: node.id,
              sourceHandle,
              animated: true,
              style: {
                stroke: sourceHandle === 'false' ? '#ef4444' : sourceHandle === 'true' ? '#10b981' : '#C43B3B',
                strokeWidth: 2,
              },
            },
            eds
          )
        );
      }
      lastHoveredRef.current = node.id;
    },
    [cmdHeld, setEdges, nodes]
  );

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

  const cleanLayout = useCallback(() => {
    const { nodes: layouted } = getLayoutedElements(nodes, edges);
    setNodes(layouted);
    setTimeout(() => fitView({ padding: 0.15, duration: 400 }), 50);
  }, [nodes, edges, setNodes, fitView]);

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
    <div className="flex flex-col h-screen bg-background text-foreground">

      {/* ── Toolbar ──────────────────────────────────────────────────────── */}
      <header className="h-12 shrink-0 flex items-center justify-between px-4 border-b border-border bg-card">
        <div className="flex items-center gap-2">
          <Link href="/dashboard" className="font-serif text-2xl tracking-tight text-foreground">
            Clarus
          </Link>
          <span className="text-muted-foreground text-sm">/</span>
          <span className="text-muted-foreground text-sm">
            {workflowName ? workflowName : 'Workflow Builder'}
          </span>

          {/* Node / edge counters */}
          {(nodes.length > 0 || edges.length > 0) && (
            <div className="flex items-center gap-1.5 ml-2">
              <span className="text-[10px] bg-muted border border-border text-muted-foreground px-2 py-0.5 rounded-full">
                {nodes.length} nodes
              </span>
              <span className="text-[10px] bg-muted border border-border text-muted-foreground px-2 py-0.5 rounded-full">
                {edges.length} edges
              </span>
            </div>
          )}

          {/* Undo / Redo */}
          <div className="flex items-center gap-0.5 ml-1">
            <button
              onClick={undo}
              disabled={!canUndo}
              title="Undo (⌘Z)"
              className="p-1 rounded hover:bg-muted text-muted-foreground disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <Undo2 className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={redo}
              disabled={!canRedo}
              title="Redo (⌘⇧Z)"
              className="p-1 rounded hover:bg-muted text-muted-foreground disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <Redo2 className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Select / Pan mode toggle */}
          <div className="flex items-center gap-0.5 ml-1 border-l border-border pl-2">
            <button
              onClick={() => setSelectMode(true)}
              title="Select mode (V)"
              className={`p-1 rounded transition-colors ${selectMode ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted'}`}
            >
              <MousePointer2 className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setSelectMode(false)}
              title="Pan mode (H)"
              className={`p-1 rounded transition-colors ${!selectMode ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted'}`}
            >
              <Hand className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="xs" onClick={openLoadModal}>
            Load Workflow
          </Button>
          <Button variant="outline" size="xs" onClick={loadExample}>
            Load Example
          </Button>
          <Button variant="outline" size="xs" onClick={clearCanvas} disabled={nodes.length === 0}>
            Clear
          </Button>
          <Button variant="outline" size="xs" onClick={exportWorkflow} disabled={nodes.length === 0}>
            Export JSON
          </Button>
          <Button variant="outline" size="xs" onClick={cleanLayout} disabled={nodes.length === 0}>
            Clean
          </Button>
          <Button
            size="xs"
            onClick={handleSaveClick}
            disabled={nodes.length === 0 || saveStatus === 'saving'}
            className={
              saveStatus === 'saved'
                ? 'bg-emerald-600 hover:bg-emerald-600 text-white'
                : saveStatus === 'error'
                  ? 'bg-red-600 hover:bg-red-600 text-white'
                  : ''
            }
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
          </Button>
          <Button
            size="xs"
            onClick={openRunModal}
            disabled={!savedWorkflowId}
            title={!savedWorkflowId ? 'Save the workflow first' : 'Run this workflow'}
            className="bg-emerald-600 hover:bg-emerald-500 text-white"
          >
            ▶&nbsp;Run
          </Button>
        </div>
      </header>

      {/* ── Body ─────────────────────────────────────────────────────────── */}
      <CmdHoverContext.Provider value={{ cmdHeld, setHandle }}>
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
            onNodeMouseEnter={onNodeMouseEnter}
            nodeTypes={nodeTypes}
            defaultEdgeOptions={defaultEdgeOptions}
            fitView
            selectionOnDrag={selectMode}
            panOnDrag={selectMode ? [1, 2] : true}
            selectionMode={SelectionMode.Partial}
            proOptions={{ hideAttribution: true }}
            deleteKeyCode="Delete"
          >
            <Background
              variant={BackgroundVariant.Dots}
              color="#EDE6E8"
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
              maskColor="rgba(250,250,248,0.7)"
            />
          </ReactFlow>

          {/* Empty-state hint */}
          {nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center space-y-2">
                <p className="text-muted-foreground text-sm">
                  Drag nodes from the palette, or
                </p>
                <p className="text-muted-foreground text-xs">
                  click{' '}
                  <span className="text-foreground bg-muted px-1.5 py-0.5 rounded font-mono">
                    Load Workflow
                  </span>{' '}
                  to reload a saved workflow, or{' '}
                  <span className="text-foreground bg-muted px-1.5 py-0.5 rounded font-mono">
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
      </CmdHoverContext.Provider>

      {/* ── Save workflow name modal ───────────────────────────────────── */}
      {showNameModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-card border border-border rounded-xl p-6 w-full max-w-md shadow-2xl">
            <h2 className="text-lg font-semibold text-foreground mb-4">Save Workflow</h2>
            <label className="block text-sm text-muted-foreground mb-1">Name *</label>
            <input
              autoFocus
              type="text"
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              placeholder="e.g. Lab Results Follow-Up"
              className="w-full px-3 py-2 rounded-lg bg-muted border border-input text-foreground text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring mb-3"
            />
            <label className="block text-sm text-muted-foreground mb-1">Description</label>
            <textarea
              value={workflowDescription}
              onChange={(e) => setWorkflowDescription(e.target.value)}
              placeholder="Optional description…"
              rows={2}
              className="w-full px-3 py-2 rounded-lg bg-muted border border-input text-foreground text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring mb-4 resize-none"
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowNameModal(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={!workflowName.trim()}
                onClick={() => doSave(workflowName.trim(), workflowDescription.trim())}
              >
                Save
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── Load Workflow modal ────────────────────────────────────────── */}
      {showLoadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-card border border-border rounded-xl p-6 w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-foreground">Load Workflow</h2>
              <button
                onClick={() => setShowLoadModal(false)}
                className="text-muted-foreground hover:text-foreground text-xl leading-none"
              >×</button>
            </div>

            {loadingWorkflows ? (
              <p className="text-sm text-muted-foreground text-center py-8">Loading workflows…</p>
            ) : loadWorkflowError ? (
              <p className="text-sm text-destructive text-center py-8">{loadWorkflowError}</p>
            ) : availableWorkflows.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">No saved workflows found.</p>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                {availableWorkflows.map((wf) => (
                  <button
                    key={wf.id}
                    onClick={() => loadWorkflow(wf)}
                    className="w-full text-left rounded-lg border border-border bg-background hover:bg-muted hover:border-primary/50 px-4 py-3 transition-colors group"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-foreground group-hover:text-primary truncate">{wf.name}</p>
                        {wf.description && (
                          <p className="text-xs text-muted-foreground mt-0.5 truncate">{wf.description}</p>
                        )}
                        <div className="flex items-center gap-3 mt-1.5">
                          <span className="text-[10px] text-muted-foreground">
                            {Array.isArray(wf.nodes) ? wf.nodes.length : 0} nodes
                          </span>
                          <span className="text-[10px] text-muted-foreground">
                            {Array.isArray(wf.edges) ? wf.edges.length : 0} edges
                          </span>
                          <span className="text-[10px] text-muted-foreground">
                            {formatDate(wf.created_at)}
                          </span>
                        </div>
                      </div>
                      <span className={`flex-shrink-0 text-[10px] px-2 py-0.5 rounded-full font-medium ${
                        wf.status === 'ENABLED'
                          ? 'bg-success/10 text-success'
                          : 'bg-muted text-muted-foreground'
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
          <div className="bg-card border border-border rounded-xl p-6 w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-lg font-semibold text-foreground">Run Workflow</h2>
              <button
                onClick={() => { setShowRunModal(false); setRunResult(null); setRunStatus('idle'); }}
                className="text-muted-foreground hover:text-foreground text-xl leading-none"
              >×</button>
            </div>
            <p className="text-xs text-muted-foreground mb-4">
              Workflow: <span className="text-primary font-medium">{workflowName}</span>
            </p>

            {/* Patient picker */}
            {runStatus === 'idle' && (
              <>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm text-muted-foreground font-medium">Select Patient</label>
                  <button
                    onClick={() => setShowAddPatient((v) => !v)}
                    className="text-xs text-primary hover:text-primary/80 transition-colors"
                  >
                    {showAddPatient ? '− Cancel' : '+ Add Patient'}
                  </button>
                </div>

                {showAddPatient && (
                  <div className="mb-3 rounded-lg border border-border bg-muted p-3 space-y-2">
                    <input
                      type="text"
                      value={newPatientName}
                      onChange={(e) => setNewPatientName(e.target.value)}
                      placeholder="Full Name"
                      className="w-full px-3 py-1.5 rounded-lg bg-background border border-input text-foreground text-xs placeholder-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                    <input
                      type="tel"
                      value={newPatientPhone}
                      onChange={(e) => setNewPatientPhone(e.target.value)}
                      placeholder="Phone (e.g. +1 555 000 0000)"
                      className="w-full px-3 py-1.5 rounded-lg bg-background border border-input text-foreground text-xs placeholder-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                    <Button
                      size="xs"
                      onClick={handleAddPatient}
                      disabled={addingPatient || !newPatientName.trim() || !newPatientPhone.trim()}
                    >
                      {addingPatient ? 'Saving…' : 'Create Patient'}
                    </Button>
                  </div>
                )}

                {loadingPatients ? (
                  <p className="text-xs text-muted-foreground mb-4">Loading patients…</p>
                ) : patients.length === 0 && !showAddPatient ? (
                  <p className="text-xs text-muted-foreground mb-4">No patients yet — add one above.</p>
                ) : (
                  <div className="space-y-1.5 max-h-48 overflow-y-auto mb-4 pr-1">
                    {patients.map((p) => (
                      <button
                        key={p.id}
                        onClick={() => setSelectedPatientId(p.id)}
                        className={`w-full text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                          selectedPatientId === p.id
                            ? 'border-primary bg-primary/10 text-foreground'
                            : 'border-border bg-background text-foreground hover:border-border hover:bg-muted'
                        }`}
                      >
                        <span className="font-medium">{p.name}</span>
                        <span className="text-xs text-muted-foreground ml-2">{p.phone}</span>
                      </button>
                    ))}
                  </div>
                )}

                <div className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => { setShowRunModal(false); }}>
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    disabled={!selectedPatientId}
                    onClick={handleRun}
                    className="bg-emerald-600 hover:bg-emerald-500 text-white"
                  >
                    ▶ Execute
                  </Button>
                </div>
              </>
            )}

            {/* Running state */}
            {runStatus === 'running' && (
              <div className="flex flex-col items-center justify-center py-10 gap-3">
                <svg className="animate-spin size-8 text-emerald-500" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                <p className="text-sm text-muted-foreground">Executing workflow…</p>
              </div>
            )}

            {/* Result state */}
            {(runStatus === 'success' || runStatus === 'error') && runResult && (
              <>
                <div className={`flex items-center gap-2 mb-4 rounded-lg px-3 py-2 ${
                  runStatus === 'success' ? 'bg-success/10 border border-success/30' : 'bg-destructive/10 border border-destructive/30'
                }`}>
                  <span className="text-sm font-semibold">
                    {runStatus === 'success' ? '✓ Completed' : '✕ Failed'}
                  </span>
                  {runResult.call_log_id && (
                    <span className="text-[10px] text-muted-foreground ml-auto">
                      Log&nbsp;ID:&nbsp;{runResult.call_log_id.slice(0, 8)}…
                    </span>
                  )}
                </div>

                <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1 mb-4">
                  {(runResult.execution_log ?? []).map((step: any, i: number) => (
                    <div key={i} className="rounded-lg bg-muted border border-border px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span
                          className="size-2 rounded-full flex-shrink-0"
                          style={{ backgroundColor: stepColor(step.status) }}
                        />
                        <span className="text-xs font-medium text-foreground">{step.label || step.node_type}</span>
                        <span className="ml-auto text-[10px] text-muted-foreground capitalize">{step.status}</span>
                      </div>
                      <p className="text-[11px] text-muted-foreground mt-0.5 pl-4">{step.message}</p>
                    </div>
                  ))}
                </div>

                <div className="flex justify-end gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => { setRunStatus('idle'); setRunResult(null); setSelectedPatientId(null); }}
                  >
                    Run Again
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => { setShowRunModal(false); setRunResult(null); setRunStatus('idle'); }}
                  >
                    Close
                  </Button>
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
