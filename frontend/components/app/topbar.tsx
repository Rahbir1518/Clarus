"use client";

import { useAuth0 } from "@auth0/auth0-react";
import {
  Search,
  Bell,
  LogOut,
  ChevronDown,
  User,
  Workflow,
  Phone,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  ArrowRight,
  X,
  Settings,
} from "lucide-react";
import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { listPatients, listWorkflows, listCallLogs } from "@/services/api";
import { cn } from "@/lib/utils";
import Link from "next/link";

type SearchResult = {
  type: "patient" | "workflow" | "call_log" | "page";
  id: string;
  title: string;
  subtitle: string;
  href: string;
};

const PAGES: SearchResult[] = [
  { type: "page", id: "dashboard", title: "Dashboard", subtitle: "Overview", href: "/dashboard" },
  { type: "page", id: "triggers", title: "Workflows & Triggers", subtitle: "Manage workflows", href: "/triggers" },
  { type: "page", id: "patients", title: "Patients", subtitle: "Patient directory", href: "/patients" },
  { type: "page", id: "calls", title: "Call Log", subtitle: "Execution history", href: "/calls" },
  { type: "page", id: "appointments", title: "Appointments", subtitle: "Scheduled visits", href: "/appointments" },
  { type: "page", id: "audit", title: "Audit Log", subtitle: "Event trail", href: "/audit-log" },
  { type: "page", id: "settings", title: "Settings", subtitle: "Account settings", href: "/settings" },
  { type: "page", id: "workflow", title: "Workflow Builder", subtitle: "Create workflows", href: "/workflow" },
];

export function Topbar() {
  const { user, logout } = useAuth0();
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [loadingNotifs, setLoadingNotifs] = useState(false);
  const [notifRead, setNotifRead] = useState(false);

  const searchRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const doctorId = user?.sub;
  const displayName = user?.name || user?.email?.split("@")[0] || "Doctor";
  const initials = displayName
    .split(" ")
    .map((n: string) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setSearchOpen(false);
      }
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotifications(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Keyboard shortcut: Ctrl+K to focus search
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        setSearchOpen(true);
      }
      if (e.key === "Escape") {
        setSearchOpen(false);
        inputRef.current?.blur();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  // Search logic
  const doSearch = useCallback(async (query: string) => {
    if (!query.trim()) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    const q = query.toLowerCase();
    const results: SearchResult[] = [];

    // Search pages
    PAGES.forEach((p) => {
      if (p.title.toLowerCase().includes(q) || p.subtitle.toLowerCase().includes(q)) {
        results.push(p);
      }
    });

    try {
      const [patients, workflows, callLogs] = await Promise.all([
        listPatients(doctorId).catch(() => []),
        listWorkflows(doctorId).catch(() => []),
        listCallLogs().catch(() => []),
      ]);

      (Array.isArray(patients) ? patients : []).forEach((p: any) => {
        if (
          p.name?.toLowerCase().includes(q) ||
          p.phone?.includes(q) ||
          p.mrn?.toLowerCase().includes(q) ||
          p.insurance?.toLowerCase().includes(q)
        ) {
          results.push({
            type: "patient",
            id: p.id,
            title: p.name,
            subtitle: `${p.phone}${p.insurance ? ` · ${p.insurance}` : ""}`,
            href: `/patients/${p.id}`,
          });
        }
      });

      (Array.isArray(workflows) ? workflows : []).forEach((w: any) => {
        if (
          w.name?.toLowerCase().includes(q) ||
          w.description?.toLowerCase().includes(q) ||
          w.category?.toLowerCase().includes(q)
        ) {
          results.push({
            type: "workflow",
            id: w.id,
            title: w.name,
            subtitle: `${w.status} · ${Array.isArray(w.nodes) ? w.nodes.length : 0} nodes`,
            href: `/workflow?id=${w.id}`,
          });
        }
      });

      (Array.isArray(callLogs) ? callLogs : []).slice(0, 50).forEach((cl: any) => {
        if (
          cl.status?.toLowerCase().includes(q) ||
          cl.outcome?.toLowerCase().includes(q) ||
          cl.id?.toLowerCase().includes(q)
        ) {
          results.push({
            type: "call_log",
            id: cl.id,
            title: `Call — ${cl.status}`,
            subtitle: `${cl.outcome || "No outcome"} · ${new Date(cl.created_at).toLocaleString()}`,
            href: "/calls",
          });
        }
      });
    } catch {
      // silently fail
    }

    setSearchResults(results.slice(0, 12));
    setSearching(false);
  }, [doctorId]);

  // Debounced search
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    const timer = setTimeout(() => doSearch(searchQuery), 300);
    return () => clearTimeout(timer);
  }, [searchQuery, doSearch]);

  const handleResultClick = (result: SearchResult) => {
    setSearchOpen(false);
    setSearchQuery("");
    router.push(result.href);
  };

  // Fetch notifications (recent call logs as notification items)
  const fetchNotifications = useCallback(async () => {
    setLoadingNotifs(true);
    try {
      const logs = await listCallLogs(undefined, doctorId);
      const items = (Array.isArray(logs) ? logs : []).slice(0, 20).map((cl: any) => ({
        id: cl.id,
        type: cl.status === "failed" ? "error" : cl.status === "completed" ? "success" : "info",
        title:
          cl.status === "failed" ? "Workflow Execution Failed" :
          cl.status === "completed" ? "Workflow Completed" :
          cl.status === "running" ? "Workflow Running" :
          "Workflow Initiated",
        message: cl.outcome
          ? `Outcome: ${cl.outcome}`
          : `Status: ${cl.status}${cl.trigger_node ? ` · Trigger: ${cl.trigger_node}` : ""}`,
        time: cl.created_at,
        href: "/calls",
      }));
      setNotifications(items);
    } catch {
      setNotifications([]);
    } finally {
      setLoadingNotifs(false);
    }
  }, []);

  const handleOpenNotifications = () => {
    setShowNotifications(!showNotifications);
    if (!showNotifications) {
      setNotifRead(true);
      fetchNotifications();
    }
  };

  const unreadCount = notifRead ? 0 : null;

  const typeIcon = (type: string) => {
    switch (type) {
      case "patient": return <User className="size-4 text-primary" />;
      case "workflow": return <Workflow className="size-4 text-violet-500" />;
      case "call_log": return <Phone className="size-4 text-emerald-500" />;
      default: return <ArrowRight className="size-4 text-muted-foreground" />;
    }
  };

  const notifIcon = (type: string) => {
    switch (type) {
      case "error": return <XCircle className="size-4 text-destructive" />;
      case "success": return <CheckCircle2 className="size-4 text-success" />;
      default: return <Clock className="size-4 text-muted-foreground" />;
    }
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur-xl">
      {/* Search */}
      <div ref={searchRef} className="flex flex-1 items-center max-w-md relative">
        <div className="relative w-full">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            ref={inputRef}
            type="text"
            placeholder="Search patients, workflows… (Ctrl+K)"
            value={searchQuery}
            onChange={(e) => { setSearchQuery(e.target.value); setSearchOpen(true); }}
            onFocus={() => setSearchOpen(true)}
            className="w-full rounded-lg border border-border bg-muted/40 py-2 pl-10 pr-10 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-colors"
          />
          {searchQuery && (
            <button
              onClick={() => { setSearchQuery(""); setSearchResults([]); }}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          )}
        </div>

        {/* Search results dropdown */}
        {searchOpen && searchQuery.trim() && (
          <div className="absolute left-0 top-full mt-2 w-full rounded-xl border border-border bg-card shadow-xl overflow-hidden z-50">
            {searching ? (
              <div className="px-4 py-6 text-center text-sm text-muted-foreground">Searching…</div>
            ) : searchResults.length === 0 ? (
              <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                No results for &quot;{searchQuery}&quot;
              </div>
            ) : (
              <div className="max-h-80 overflow-y-auto">
                {searchResults.map((r) => (
                  <button
                    key={`${r.type}-${r.id}`}
                    onClick={() => handleResultClick(r)}
                    className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/50 transition-colors border-b border-border/50 last:border-0"
                  >
                    {typeIcon(r.type)}
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{r.title}</p>
                      <p className="text-[11px] text-muted-foreground truncate">{r.subtitle}</p>
                    </div>
                    <span className="text-[9px] uppercase tracking-wider text-muted-foreground bg-muted px-1.5 py-0.5 rounded shrink-0">
                      {r.type === "call_log" ? "call" : r.type}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3">
        {/* Notifications */}
        <div ref={notifRef} className="relative">
          <button
            onClick={handleOpenNotifications}
            className="relative rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Bell className="size-5" />
            {!notifRead && (
              <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-destructive" />
            )}
          </button>

          {/* Notifications dropdown */}
          {showNotifications && (
            <div className="absolute right-0 top-full mt-2 w-96 rounded-xl border border-border bg-card shadow-xl overflow-hidden z-50">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <h3 className="text-sm font-semibold">Notifications</h3>
                <Link
                  href="/calls"
                  onClick={() => setShowNotifications(false)}
                  className="text-[11px] text-primary hover:underline"
                >
                  View all calls
                </Link>
              </div>
              {loadingNotifs ? (
                <div className="px-4 py-8 text-center text-sm text-muted-foreground">Loading…</div>
              ) : notifications.length === 0 ? (
                <div className="px-4 py-8 text-center text-sm text-muted-foreground">No notifications yet.</div>
              ) : (
                <div className="max-h-96 overflow-y-auto">
                  {notifications.map((n) => (
                    <Link
                      key={n.id}
                      href={n.href}
                      onClick={() => setShowNotifications(false)}
                      className={cn(
                        "flex items-start gap-3 px-4 py-3 border-b border-border/50 last:border-0 hover:bg-muted/30 transition-colors",
                        n.type === "error" && "bg-destructive/3"
                      )}
                    >
                      <div className="mt-0.5 shrink-0">{notifIcon(n.type)}</div>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium">{n.title}</p>
                        <p className="text-[11px] text-muted-foreground mt-0.5">{n.message}</p>
                        <p className="text-[10px] text-muted-foreground mt-1">
                          {formatRelativeTime(n.time)}
                        </p>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="h-8 w-px bg-border" />

        {/* User profile */}
        <div className="relative">
          <button
            onClick={() => setShowMenu(!showMenu)}
            className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 transition-colors hover:bg-muted"
          >
            <div className="flex size-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
              {initials}
            </div>
            <div className="hidden text-left sm:block">
              <p className="text-sm font-medium leading-tight">{displayName}</p>
              <p className="text-[11px] leading-tight text-muted-foreground">Physician</p>
            </div>
            <ChevronDown className="size-3.5 text-muted-foreground" />
          </button>

          {showMenu && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowMenu(false)} />
              <div className="absolute right-0 top-full z-50 mt-1 w-52 rounded-xl border border-border bg-card shadow-lg">
                <div className="border-b border-border px-4 py-3">
                  <p className="text-sm font-medium">{displayName}</p>
                  <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
                </div>
                <div className="p-1">
                  <Link
                    href="/settings"
                    onClick={() => setShowMenu(false)}
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-foreground transition-colors hover:bg-muted"
                  >
                    <Settings className="size-4" />
                    Settings
                  </Link>
                  <button
                    onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-destructive transition-colors hover:bg-destructive/10"
                  >
                    <LogOut className="size-4" />
                    Sign Out
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

function formatRelativeTime(isoString: string): string {
  try {
    const now = Date.now();
    const then = new Date(isoString).getTime();
    const diffMs = now - then;
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "Just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 7) return `${diffDay}d ago`;
    return new Date(isoString).toLocaleDateString();
  } catch {
    return isoString;
  }
}
