"use client";

import { useClerk, useUser } from "@clerk/nextjs";
import {
  Bell,
  LogOut,
  ChevronDown,
  CheckCircle2,
  XCircle,
  Clock,
  Settings,
} from "lucide-react";
import { useState, useEffect, useCallback, useRef } from "react";
import { listCallLogs } from "@/services/api";
import { cn } from "@/lib/utils";
import Link from "next/link";

export function Topbar() {
  const { user } = useUser();
  const { signOut } = useClerk();
  const [showMenu, setShowMenu] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [loadingNotifs, setLoadingNotifs] = useState(false);
  const [notifRead, setNotifRead] = useState(false);

  const notifRef = useRef<HTMLDivElement>(null);

  const doctorId = user?.id;
  const displayName =
    user?.fullName || user?.primaryEmailAddress?.emailAddress?.split("@")[0] || "Doctor";
  const initials = displayName
    .split(" ")
    .map((n: string) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotifications(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

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

  const notifIcon = (type: string) => {
    switch (type) {
      case "error": return <XCircle className="size-4 text-destructive" />;
      case "success": return <CheckCircle2 className="size-4 text-success" />;
      default: return <Clock className="size-4 text-muted-foreground" />;
    }
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-end border-b border-border bg-background/80 px-6 backdrop-blur-xl">
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
                  <p className="text-xs text-muted-foreground truncate">
                    {user?.primaryEmailAddress?.emailAddress}
                  </p>
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
                    onClick={() => signOut({ redirectUrl: "/" })}
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
