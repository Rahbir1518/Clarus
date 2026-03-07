"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { listCallLogs } from "@/services/api";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  ClipboardList,
  Search,
  X,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  RefreshCw,
} from "lucide-react";

const statusConfig: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; color: string }> = {
  completed: { label: "Completed", icon: CheckCircle2, color: "text-success" },
  failed: { label: "Failed", icon: XCircle, color: "text-destructive" },
  running: { label: "Running", icon: Loader2, color: "text-primary" },
  initiated: { label: "Initiated", icon: Clock, color: "text-muted-foreground" },
};

export default function AuditLogPage() {
  const { user } = useAuth0();
  const doctorId = user?.sub;

  const [callLogs, setCallLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  const fetchCallLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listCallLogs(undefined, doctorId);
      setCallLogs(Array.isArray(data) ? data : []);
    } catch {
      setCallLogs([]);
    } finally {
      setLoading(false);
    }
  }, [doctorId]);

  useEffect(() => {
    fetchCallLogs();
  }, [fetchCallLogs]);

  const allEvents = callLogs.flatMap((cl) => {
    const execLog: any[] = Array.isArray(cl.execution_log) ? cl.execution_log : [];
    const events = execLog.map((step, i) => ({
      id: `${cl.id}-${i}`,
      callLogId: cl.id,
      workflowId: cl.workflow_id,
      patientId: cl.patient_id,
      nodeType: step.node_type || "unknown",
      label: step.label || step.node_type || "Step",
      message: step.message || "",
      status: step.status || "unknown",
      timestamp: cl.created_at,
    }));

    if (events.length === 0) {
      events.push({
        id: cl.id,
        callLogId: cl.id,
        workflowId: cl.workflow_id,
        patientId: cl.patient_id,
        nodeType: "workflow_execution",
        label: `Workflow Execution — ${cl.status}`,
        message: cl.outcome || `Status: ${cl.status}`,
        status: cl.status === "completed" ? "ok" : cl.status === "failed" ? "error" : "info",
        timestamp: cl.created_at,
      });
    }

    return events;
  });

  const filtered = allEvents.filter((ev) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      ev.label?.toLowerCase().includes(q) ||
      ev.message?.toLowerCase().includes(q) ||
      ev.nodeType?.toLowerCase().includes(q) ||
      ev.callLogId?.toLowerCase().includes(q)
    );
  });

  const statusDot = (s: string) => {
    if (s === "ok") return "bg-success";
    if (s === "error") return "bg-destructive";
    if (s === "info") return "bg-primary";
    return "bg-muted-foreground";
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Audit Log</h1>
          <p className="text-sm text-muted-foreground">
            Complete audit trail of all workflow execution events.
            {!loading && ` ${allEvents.length} event${allEvents.length !== 1 ? "s" : ""} across ${callLogs.length} execution${callLogs.length !== 1 ? "s" : ""}.`}
          </p>
        </div>
        <Button variant="outline" onClick={fetchCallLogs}>
          <RefreshCw className="size-4" />
          Refresh
        </Button>
      </div>

      {/* Search */}
      <div className="relative max-w-xs">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search events…"
          className="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-background text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
        />
        {search && (
          <button onClick={() => setSearch("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
            <X className="size-3.5" />
          </button>
        )}
      </div>

      {/* Events */}
      {loading ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center text-sm text-muted-foreground">
          Loading audit log…
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center">
          <ClipboardList className="size-10 text-muted-foreground/40 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">
            {allEvents.length === 0
              ? "No events recorded yet."
              : "No events match your search."}
          </p>
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground w-8"></th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Event</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Type</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Message</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">IDs</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Time</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((ev) => (
                <tr key={ev.id} className="border-b border-border/50 last:border-0 hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3">
                    <span className={cn("block size-2 rounded-full", statusDot(ev.status))} />
                  </td>
                  <td className="px-4 py-3 font-medium text-xs">{ev.label}</td>
                  <td className="px-4 py-3">
                    <code className="bg-muted px-1.5 py-0.5 rounded text-[10px] font-mono">{ev.nodeType}</code>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground max-w-xs truncate">{ev.message}</td>
                  <td className="px-4 py-3 text-[10px] text-muted-foreground">
                    <div>Log: {ev.callLogId?.slice(0, 8)}…</div>
                    {ev.patientId && <div>Patient: {ev.patientId.slice(0, 8)}…</div>}
                  </td>
                  <td className="px-4 py-3 text-[10px] text-muted-foreground whitespace-nowrap">
                    {new Date(ev.timestamp).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
