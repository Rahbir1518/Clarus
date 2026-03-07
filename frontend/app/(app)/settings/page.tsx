"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { Button } from "@/components/ui/button";
import { User, Mail, Shield, LogOut, ExternalLink } from "lucide-react";

export default function SettingsPage() {
  const { user, isAuthenticated, logout } = useAuth0();

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Account and application settings.
        </p>
      </div>

      {/* Profile */}
      <div className="rounded-xl border border-border bg-card">
        <div className="border-b border-border px-5 py-4">
          <h3 className="text-sm font-semibold">Profile</h3>
          <p className="text-xs text-muted-foreground mt-0.5">Your account information from Auth0.</p>
        </div>
        <div className="p-5 space-y-4">
          {isAuthenticated && user ? (
            <>
              <div className="flex items-center gap-4">
                {user.picture ? (
                  <img
                    src={user.picture}
                    alt={user.name || "User"}
                    className="size-14 rounded-full border border-border"
                  />
                ) : (
                  <div className="flex size-14 items-center justify-center rounded-full bg-primary text-lg font-bold text-primary-foreground">
                    {user.name?.charAt(0)?.toUpperCase() || "U"}
                  </div>
                )}
                <div>
                  <p className="text-base font-semibold">{user.name || "—"}</p>
                  <p className="text-sm text-muted-foreground">{user.email || "—"}</p>
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <InfoRow icon={User} label="Name" value={user.name || "—"} />
                <InfoRow icon={Mail} label="Email" value={user.email || "—"} />
                <InfoRow icon={Shield} label="Auth0 ID" value={user.sub || "—"} />
                <InfoRow icon={ExternalLink} label="Provider" value={user.sub?.split("|")[0] || "—"} />
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Not authenticated.</p>
          )}
        </div>
      </div>

      {/* App info */}
      <div className="rounded-xl border border-border bg-card">
        <div className="border-b border-border px-5 py-4">
          <h3 className="text-sm font-semibold">Application</h3>
        </div>
        <div className="p-5 space-y-3">
          <InfoRow icon={Shield} label="App" value="Clarus — Clinical Workflow Automation" />
          <InfoRow icon={ExternalLink} label="API" value={process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"} />
          <InfoRow icon={ExternalLink} label="Auth0 Domain" value={process.env.NEXT_PUBLIC_AUTH0_DOMAIN || "—"} />
        </div>
      </div>

      {/* Sign out */}
      {isAuthenticated && (
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold">Sign Out</h3>
              <p className="text-xs text-muted-foreground mt-0.5">End your session and return to the login page.</p>
            </div>
            <Button
              variant="outline"
              onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
              className="text-destructive hover:text-destructive hover:bg-destructive/10"
            >
              <LogOut className="size-4" />
              Sign Out
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function InfoRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-2">
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="text-sm font-medium truncate">{value}</p>
      </div>
    </div>
  );
}
