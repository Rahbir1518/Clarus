"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import {
  listWorkflows,
  deleteWorkflow,
  updateWorkflow,
} from "@/services/api";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Zap,
  Plus,
  Trash2,
  ArrowRight,
  ToggleLeft,
  ToggleRight,
  Workflow,
  Clock,
  Search,
  X,
} from "lucide-react";

export default function TriggersPage() {
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<"all" | "DRAFT" | "ENABLED">("all");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const { user } = useAuth0();
  const doctorId = user?.sub;

  const fetchWorkflows = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listWorkflows(doctorId);
      setWorkflows(Array.isArray(data) ? data : []);
    } catch {
      setWorkflows([]);
    } finally {
      setLoading(false);
    }
  }, [doctorId]);

  useEffect(() => {
    fetchWorkflows();
  }, [fetchWorkflows]);

  const handleDelete = useCallback(async (id: string) => {
    if (!confirm("Delete this workflow? This cannot be undone.")) return;
    setDeletingId(id);
    try {
      await deleteWorkflow(id);
      setWorkflows((prev) => prev.filter((w) => w.id !== id));
    } catch {
      /* ignore */
    } finally {
      setDeletingId(null);
    }
  }, []);

  const handleToggleStatus = useCallback(async (wf: any) => {
    setTogglingId(wf.id);
    const newStatus = wf.status === "ENABLED" ? "DRAFT" : "ENABLED";
    try {
      const updated = await updateWorkflow(wf.id, { status: newStatus });
      setWorkflows((prev) =>
        prev.map((w) => (w.id === wf.id ? { ...w, ...updated } : w))
      );
    } catch {
      /* ignore */
    } finally {
      setTogglingId(null);
    }
  }, []);

  const filtered = workflows.filter((wf) => {
    if (filterStatus !== "all" && wf.status !== filterStatus) return false;
    if (search && !wf.name?.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Workflows & Triggers</h1>
          <p className="text-sm text-muted-foreground">
            Manage your automated workflow triggers. Enable workflows to auto-execute on lab events.
          </p>
        </div>
        <Link href="/workflow">
          <Button>
            <Plus className="size-4" />
            New Workflow
          </Button>
        </Link>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search workflows…"
            className="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-background text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          />
          {search && (
            <button onClick={() => setSearch("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
              <X className="size-3.5" />
            </button>
          )}
        </div>
        <div className="flex items-center rounded-lg border border-border overflow-hidden">
          {(["all", "ENABLED", "DRAFT"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={cn(
                "px-3 py-1.5 text-xs font-medium transition-colors",
                filterStatus === s
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted"
              )}
            >
              {s === "all" ? "All" : s}
            </button>
          ))}
        </div>
      </div>

      {/* Workflow list */}
      {loading ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center text-sm text-muted-foreground">
          Loading workflows…
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center">
          <Workflow className="size-10 text-muted-foreground/40 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">
            {workflows.length === 0
              ? "No workflows yet. Create one to get started."
              : "No workflows match your filters."}
          </p>
          {workflows.length === 0 && (
            <Link href="/workflow">
              <Button size="sm" className="mt-3">Create Workflow</Button>
            </Link>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((wf) => (
            <div
              key={wf.id}
              className="rounded-xl border border-border bg-card p-5 hover:border-primary/20 transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Zap className={cn("size-4", wf.status === "ENABLED" ? "text-success" : "text-muted-foreground")} />
                    <h3 className="text-sm font-semibold">{wf.name}</h3>
                    <span
                      className={cn(
                        "inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold",
                        wf.status === "ENABLED"
                          ? "bg-success/10 text-success"
                          : "bg-muted text-muted-foreground"
                      )}
                    >
                      {wf.status}
                    </span>
                    {wf.category && wf.category !== "Ungrouped" && (
                      <span className="text-[10px] text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                        {wf.category}
                      </span>
                    )}
                  </div>
                  {wf.description && (
                    <p className="text-xs text-muted-foreground mt-1">{wf.description}</p>
                  )}
                  <div className="flex items-center gap-4 mt-2">
                    <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                      <Workflow className="size-3" />
                      {Array.isArray(wf.nodes) ? wf.nodes.length : 0} nodes
                    </span>
                    <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                      <Clock className="size-3" />
                      {new Date(wf.updated_at || wf.created_at).toLocaleDateString()}
                    </span>
                    <code className="text-[10px] text-muted-foreground bg-muted rounded px-1.5 py-0.5">
                      {wf.id.slice(0, 8)}…
                    </code>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={togglingId === wf.id}
                    onClick={() => handleToggleStatus(wf)}
                    title={wf.status === "ENABLED" ? "Disable workflow" : "Enable workflow"}
                  >
                    {wf.status === "ENABLED" ? (
                      <ToggleRight className="size-4 text-success" />
                    ) : (
                      <ToggleLeft className="size-4" />
                    )}
                  </Button>
                  <Link href={`/workflow?id=${wf.id}`}>
                    <Button size="sm" variant="outline">
                      Edit
                      <ArrowRight className="size-3" />
                    </Button>
                  </Link>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={deletingId === wf.id}
                    onClick={() => handleDelete(wf.id)}
                    className="text-destructive hover:text-destructive hover:bg-destructive/10"
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
