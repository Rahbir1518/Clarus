"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { listCallLogs } from "@/services/api";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Phone,
  ChevronDown,
  ChevronRight,
  Search,
  X,
  FileText,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
} from "lucide-react";

const statusConfig: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; color: string }> = {
  completed: { label: "Completed", icon: CheckCircle2, color: "bg-success/10 text-success" },
  failed: { label: "Failed", icon: XCircle, color: "bg-destructive/10 text-destructive" },
  running: { label: "Running", icon: Loader2, color: "bg-primary/10 text-primary" },
  initiated: { label: "Initiated", icon: Clock, color: "bg-muted text-muted-foreground" },
};

export default function CallsPage() {
  const { user } = useAuth0();
  const doctorId = user?.sub;

  const [callLogs, setCallLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>("all");

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

  const filtered = callLogs.filter((cl) => {
    if (filterStatus !== "all" && cl.status !== filterStatus) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        cl.id?.toLowerCase().includes(q) ||
        cl.workflow_id?.toLowerCase().includes(q) ||
        cl.patient_id?.toLowerCase().includes(q) ||
        cl.outcome?.toLowerCase().includes(q) ||
        cl.status?.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Call Log</h1>
        <p className="text-sm text-muted-foreground">
          All workflow executions with outcomes and details.
          {!loading && ` ${callLogs.length} total execution${callLogs.length !== 1 ? "s" : ""}.`}
        </p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by ID, outcome…"
            className="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-background text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          />
          {search && (
            <button onClick={() => setSearch("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
              <X className="size-3.5" />
            </button>
          )}
        </div>
        <div className="flex items-center rounded-lg border border-border overflow-hidden">
          {["all", "completed", "running", "failed", "initiated"].map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={cn(
                "px-3 py-1.5 text-xs font-medium transition-colors capitalize",
                filterStatus === s
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted"
              )}
            >
              {s === "all" ? "All" : s}
            </button>
          ))}
        </div>
        <Button size="sm" variant="outline" onClick={fetchCallLogs}>
          Refresh
        </Button>
      </div>

      {/* Call log list */}
      {loading ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center text-sm text-muted-foreground">
          Loading call logs…
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center">
          <FileText className="size-10 text-muted-foreground/40 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">
            {callLogs.length === 0
              ? "No call logs yet. Execute a workflow to see logs here."
              : "No logs match your filters."}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((cl) => {
            const isExpanded = expandedId === cl.id;
            const config = statusConfig[cl.status] || statusConfig.initiated;
            const StatusIcon = config.icon;
            const execLog: any[] = Array.isArray(cl.execution_log) ? cl.execution_log : [];

            return (
              <div key={cl.id} className="rounded-xl border border-border bg-card overflow-hidden">
                <button
                  onClick={() => setExpandedId(isExpanded ? null : cl.id)}
                  className="w-full flex items-center gap-4 px-5 py-4 text-left hover:bg-muted/30 transition-colors"
                >
                  <div className="shrink-0">
                    {isExpanded ? <ChevronDown className="size-4 text-muted-foreground" /> : <ChevronRight className="size-4 text-muted-foreground" />}
                  </div>
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold", config.color)}>
                      <StatusIcon className="size-3" />
                      {config.label}
                    </span>
                    {cl.outcome && (
                      <span className="text-xs text-muted-foreground capitalize">{cl.outcome}</span>
                    )}
                    {cl.trigger_node && (
                      <span className="text-[10px] bg-muted text-muted-foreground px-2 py-0.5 rounded-full">{cl.trigger_node}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-4 shrink-0 text-[11px] text-muted-foreground">
                    <span>Workflow: {cl.workflow_id?.slice(0, 8) ?? "—"}…</span>
                    <span>Patient: {cl.patient_id?.slice(0, 8) ?? "—"}…</span>
                    <span>{new Date(cl.created_at).toLocaleString()}</span>
                  </div>
                </button>

                {isExpanded && (
                  <div className="border-t border-border px-5 py-4 bg-muted/10">
                    <div className="grid grid-cols-2 gap-4 mb-4 text-xs">
                      <div>
                        <span className="text-muted-foreground">Call Log ID:</span>
                        <code className="ml-2 rounded bg-muted px-2 py-0.5 font-mono text-xs">{cl.id}</code>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Workflow ID:</span>
                        <code className="ml-2 rounded bg-muted px-2 py-0.5 font-mono text-xs">{cl.workflow_id ?? "—"}</code>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Patient ID:</span>
                        <code className="ml-2 rounded bg-muted px-2 py-0.5 font-mono text-xs">{cl.patient_id ?? "—"}</code>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Keypress:</span>
                        <span className="ml-2">{cl.keypress || "—"}</span>
                      </div>
                    </div>

                    {execLog.length > 0 ? (
                      <div>
                        <h4 className="text-xs font-semibold mb-2">Execution Steps</h4>
                        <div className="space-y-1.5">
                          {execLog.map((step: any, i: number) => (
                            <div key={i} className="flex items-start gap-2 rounded-lg bg-card border border-border px-3 py-2">
                              <span
                                className="mt-1 size-2 rounded-full shrink-0"
                                style={{
                                  backgroundColor:
                                    step.status === "ok" ? "#10b981"
                                    : step.status === "error" ? "#ef4444"
                                    : "#6b7280",
                                }}
                              />
                              <div className="min-w-0 flex-1">
                                <p className="text-xs font-medium">{step.label || step.node_type}</p>
                                <p className="text-[11px] text-muted-foreground">{step.message}</p>
                              </div>
                              <span className="text-[10px] text-muted-foreground capitalize shrink-0">{step.status}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">No execution steps recorded.</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
