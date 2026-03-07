"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { listPatients, createPatient } from "@/services/api";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Phone,
  CheckCircle2,
  TrendingUp,
  Zap,
  Calendar,
  AlertTriangle,
  Clock,
  ClipboardCheck,
  AlertCircle,
  ArrowRight,
  Lightbulb,
  FlaskConical,
  UserCheck,
  ClipboardEdit,
  Send,
  Hash,
  Shield,
  Stethoscope,
  User,
  Activity,
  ArrowUpRight,
  UserPlus,
  X,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const STATS = [
  { label: "Calls Today", value: "12", icon: Phone, trend: "+18%", trendUp: true },
  { label: "Confirmed", value: "8", icon: CheckCircle2, trend: "+5%", trendUp: true },
  { label: "Answer Rate", value: "72%", icon: TrendingUp, trend: null, trendUp: false },
  { label: "Active Triggers", value: "5", icon: Zap, trend: null, trendUp: false },
];

const PATIENT = {
  name: "James Thompson",
  initials: "JT",
  dob: "May 15, 1978",
  age: 47,
  mrn: "MRN-2024-0847",
  insurance: "Blue Cross Blue Shield — PPO",
  lastVisit: "Feb 28, 2026",
  physician: "Dr. Priya Nair",
  riskLevel: "high" as const,
};

const CONDITIONS = [
  { icd10: "E11.65", description: "Type 2 Diabetes with Hyperglycemia", hcc: "HCC 19", risk: "high" as const, status: "documented" as const },
  { icd10: "I10", description: "Essential Hypertension", hcc: "HCC 85", risk: "moderate" as const, status: "documented" as const },
  { icd10: "E78.5", description: "Dyslipidemia, unspecified", hcc: "N/A", risk: "low" as const, status: "review_needed" as const },
  { icd10: "N18.3", description: "Chronic Kidney Disease, Stage 3", hcc: "HCC 138", risk: "high" as const, status: "pending_review" as const },
];

const TRIGGERS = [
  { id: "TRG-001", event: "Blood Test Result Received", classification: "Type 2 Diabetes with Hyperglycemia detected", impact: "high" as const, status: "ready" as const, time: "Today, 9:42 AM" },
  { id: "TRG-002", event: "Abnormal Lab Values", classification: "Creatinine elevated — eGFR declining", impact: "medium" as const, status: "pending" as const, time: "Today, 8:15 AM" },
  { id: "TRG-003", event: "Routine Panel Complete", classification: "Annual wellness blood panel completed", impact: "low" as const, status: "processed" as const, time: "Yesterday, 4:30 PM" },
];

const INSIGHTS = [
  { type: "gap" as const, title: "Follow-up Required", description: "Patient requires follow-up after abnormal blood report received today.", priority: "high" as const },
  { type: "recommendation" as const, title: "HbA1c Follow-up", description: "Schedule HbA1c re-test within 2 weeks based on current levels.", priority: "medium" as const },
  { type: "status" as const, title: "2 Triggers Pending", description: "Review and approve pending triggers to initiate patient outreach.", priority: "medium" as const },
  { type: "metric" as const, title: "3 Calls This Week", description: "Automated calls placed for your patients. 2 confirmed, 1 pending callback.", priority: "info" as const },
];

const WORKFLOW_STEPS = [
  { label: "Review Patient", icon: UserCheck, status: "completed" as const },
  { label: "Identify Triggers", icon: Zap, status: "active" as const },
  { label: "Confirm Data", icon: ClipboardEdit, status: "upcoming" as const },
  { label: "Submit / Activate", icon: Send, status: "upcoming" as const },
];

// ---------------------------------------------------------------------------
// Style maps
// ---------------------------------------------------------------------------

const riskStyles = {
  high: "bg-destructive/10 text-destructive",
  moderate: "bg-warning/10 text-warning",
  low: "bg-success/10 text-success",
};

const conditionStatusConfig = {
  documented: { label: "Documented", icon: ClipboardCheck, color: "text-success" },
  review_needed: { label: "Review Needed", icon: AlertCircle, color: "text-warning" },
  pending_review: { label: "Pending Review", icon: Clock, color: "text-muted-foreground" },
};

const impactStyles = {
  high: { label: "High Impact", dot: "bg-destructive", border: "border-destructive/20 bg-destructive/5" },
  medium: { label: "Medium Impact", dot: "bg-warning", border: "border-warning/20 bg-warning/5" },
  low: { label: "Low Impact", dot: "bg-success", border: "border-success/20 bg-success/5" },
};

const triggerStatusConfig = {
  ready: { label: "Ready for Review", icon: AlertTriangle, color: "text-warning bg-warning/10" },
  pending: { label: "Pending", icon: FlaskConical, color: "text-muted-foreground bg-muted" },
  processed: { label: "Auto-processed", icon: CheckCircle2, color: "text-success bg-success/10" },
};

const insightIcons = { gap: AlertCircle, recommendation: Lightbulb, status: Clock, metric: Phone };
const insightBorder = { high: "border-l-destructive", medium: "border-l-warning", info: "border-l-primary" };

const stepStyles = {
  completed: { circle: "bg-primary text-primary-foreground", label: "text-primary font-semibold", connector: "bg-primary" },
  active: { circle: "bg-card border-2 border-primary text-primary ring-4 ring-primary/10", label: "text-primary font-semibold", connector: "bg-border" },
  upcoming: { circle: "bg-muted text-muted-foreground border border-border", label: "text-muted-foreground", connector: "bg-border" },
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  // ── Patient management state ──────────────────────────────────────────
  const [patients, setPatients] = useState<any[]>([]);
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [showAddPatient, setShowAddPatient] = useState(false);
  const [patientName, setPatientName] = useState("");
  const [patientPhone, setPatientPhone] = useState("");
  const [savingPatient, setSavingPatient] = useState(false);

  const { user } = useAuth0();
  const doctorId = user?.sub;

  const fetchPatients = useCallback(async () => {
    setLoadingPatients(true);
    try {
      const data = await listPatients(doctorId);
      setPatients(Array.isArray(data) ? data : []);
    } catch {
      setPatients([]);
    } finally {
      setLoadingPatients(false);
    }
  }, [doctorId]);

  useEffect(() => { fetchPatients(); }, [fetchPatients]);

  const handleAddPatient = useCallback(async () => {
    if (!patientName.trim() || !patientPhone.trim()) return;
    setSavingPatient(true);
    try {
      await createPatient({
        name: patientName.trim(),
        phone: patientPhone.trim(),
        doctor_id: doctorId ?? "unknown",
      });
      setPatientName("");
      setPatientPhone("");
      setShowAddPatient(false);
      fetchPatients();
    } catch {
      /* ignore */
    } finally {
      setSavingPatient(false);
    }
  }, [patientName, patientPhone, doctorId, fetchPatients]);

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Overview of your clinic&apos;s automation activity.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setShowAddPatient(true)}>
            <UserPlus className="size-4" data-icon="inline-start" />
            Add Patient
          </Button>
          <Link href="/triggers">
            <Button>
              <Zap className="size-4" data-icon="inline-start" />
              Manage Triggers
            </Button>
          </Link>
        </div>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {STATS.map((s) => (
          <div key={s.label} className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center justify-between">
              <s.icon className="size-4 text-muted-foreground" />
              {s.trend && (
                <span className="flex items-center gap-0.5 text-[11px] font-medium text-success">
                  <ArrowUpRight className="size-3" />
                  {s.trend}
                </span>
              )}
            </div>
            <p className="mt-2 text-2xl font-bold">{s.value}</p>
            <p className="text-xs text-muted-foreground">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Patient Management card */}
      <div className="rounded-xl border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div className="flex items-center gap-2">
            <User className="size-4 text-primary" />
            <div>
              <h3 className="text-sm font-semibold">Patients</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {loadingPatients ? "Loading…" : `${patients.length} patient${patients.length !== 1 ? "s" : ""} registered`}
              </p>
            </div>
          </div>
          <Button size="sm" variant="outline" onClick={() => setShowAddPatient(true)}>
            <UserPlus className="size-3.5" data-icon="inline-start" />
            Add Patient
          </Button>
        </div>

        {loadingPatients ? (
          <div className="px-5 py-6 text-sm text-muted-foreground">Loading patients…</div>
        ) : patients.length === 0 ? (
          <div className="px-5 py-6 text-sm text-muted-foreground">No patients yet. Add one to get started.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  {["Name", "Phone", "ID"].map((h) => (
                    <th key={h} className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {patients.map((p) => (
                  <tr key={p.id} className="border-b border-border/50 last:border-0 hover:bg-muted/30">
                    <td className="px-5 py-3 font-medium">{p.name}</td>
                    <td className="px-5 py-3 text-muted-foreground">{p.phone}</td>
                    <td className="px-5 py-3">
                      <code className="rounded bg-muted px-2 py-0.5 font-mono text-xs">{p.id.slice(0, 8)}…</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add Patient modal */}
      {showAddPatient && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-card border border-border rounded-xl p-6 w-full max-w-sm shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold">Add Patient</h2>
              <button onClick={() => setShowAddPatient(false)} className="text-muted-foreground hover:text-foreground">
                <X className="size-4" />
              </button>
            </div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Full Name *</label>
            <input
              autoFocus
              type="text"
              value={patientName}
              onChange={(e) => setPatientName(e.target.value)}
              placeholder="e.g. Jane Doe"
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary mb-3"
            />
            <label className="block text-xs font-medium text-muted-foreground mb-1">Phone Number *</label>
            <input
              type="tel"
              value={patientPhone}
              onChange={(e) => setPatientPhone(e.target.value)}
              placeholder="e.g. +1 555 000 0000"
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary mb-4"
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowAddPatient(false)}>Cancel</Button>
              <Button
                size="sm"
                disabled={savingPatient || !patientName.trim() || !patientPhone.trim()}
                onClick={handleAddPatient}
              >
                {savingPatient ? "Saving…" : "Save Patient"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Main two-column area */}
      <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
        {/* Left column */}
        <div className="space-y-6">
          {/* Patient summary */}
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-start gap-4">
              <div className="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary text-lg font-bold text-primary-foreground">
                {PATIENT.initials}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="text-xl font-bold">{PATIENT.name}</h2>
                  <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold", riskStyles[PATIENT.riskLevel])}>
                    <AlertTriangle className="size-3" />
                    High Risk
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2.5 lg:grid-cols-3">
                  <InfoItem icon={Calendar} label="Date of Birth" value={`${PATIENT.dob} (Age ${PATIENT.age})`} />
                  <InfoItem icon={Hash} label="MRN" value={PATIENT.mrn} />
                  <InfoItem icon={Shield} label="Insurance" value={PATIENT.insurance} />
                  <InfoItem icon={User} label="Last Visit" value={PATIENT.lastVisit} />
                  <InfoItem icon={Stethoscope} label="Primary Physician" value={PATIENT.physician} />
                </div>
              </div>
            </div>
          </div>

          {/* Conditions table */}
          <div className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <h3 className="text-sm font-semibold">Active Problem / Condition List</h3>
                <p className="mt-0.5 text-xs text-muted-foreground">{CONDITIONS.length} active conditions on record</p>
              </div>
              <span className="rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground">ICD-10 / HCC</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {["ICD-10", "Condition", "HCC Category", "Risk Impact", "Status", ""].map((h) => (
                      <th key={h} className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {CONDITIONS.map((c, i) => {
                    const st = conditionStatusConfig[c.status];
                    const StIcon = st.icon;
                    return (
                      <tr key={i} className="border-b border-border/50 last:border-0 transition-colors hover:bg-muted/30">
                        <td className="px-5 py-3">
                          <code className="rounded bg-muted px-2 py-0.5 font-mono text-xs">{c.icd10}</code>
                        </td>
                        <td className="px-5 py-3 font-medium">{c.description}</td>
                        <td className="px-5 py-3 text-muted-foreground">{c.hcc}</td>
                        <td className="px-5 py-3">
                          <span className={cn("inline-flex rounded-full border border-transparent px-2 py-0.5 text-xs font-semibold", riskStyles[c.risk])}>
                            {c.risk.charAt(0).toUpperCase() + c.risk.slice(1)}
                          </span>
                        </td>
                        <td className="px-5 py-3">
                          <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", st.color)}>
                            <StIcon className="size-3.5" />
                            {st.label}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-right">
                          {c.status !== "documented" && (
                            <Button variant="ghost" size="sm">Review</Button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Trigger review */}
          <div className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div className="flex items-center gap-2">
                <Zap className="size-4 text-primary" />
                <div>
                  <h3 className="text-sm font-semibold">Trigger Review</h3>
                  <p className="mt-0.5 text-xs text-muted-foreground">Automation events requiring attention</p>
                </div>
              </div>
              <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
                {TRIGGERS.filter((t) => t.status !== "processed").length} pending
              </span>
            </div>
            <div className="space-y-3 p-4">
              {TRIGGERS.map((t) => {
                const impact = impactStyles[t.impact];
                const status = triggerStatusConfig[t.status];
                const SIcon = status.icon;
                return (
                  <div key={t.id} className={cn("rounded-lg border p-4 transition-colors", t.status === "ready" ? "border-primary/20 bg-primary/3" : "border-border bg-card")}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className="text-sm font-semibold">{t.event}</h4>
                          <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium", impact.border)}>
                            <span className={cn("size-1.5 rounded-full", impact.dot)} />
                            {impact.label}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">{t.classification}</p>
                        <div className="mt-2 flex items-center gap-3">
                          <span className="text-[11px] text-muted-foreground">{t.id}</span>
                          <span className="text-[11px] text-muted-foreground">{t.time}</span>
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <span className={cn("inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium", status.color)}>
                          <SIcon className="size-3" />
                          {status.label}
                        </span>
                        {t.status === "ready" && (
                          <Button size="sm">
                            Review
                            <ArrowRight className="size-3" data-icon="inline-end" />
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Workflow progress */}
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="mb-5">
              <h3 className="text-sm font-semibold">Workflow Progress</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">Current automation lifecycle status</p>
            </div>
            <div className="flex items-center">
              {WORKFLOW_STEPS.map((step, idx) => {
                const s = stepStyles[step.status];
                const Icon = step.icon;
                const isLast = idx === WORKFLOW_STEPS.length - 1;
                return (
                  <div key={idx} className={cn("flex items-center", isLast ? "" : "flex-1")}>
                    <div className="flex flex-col items-center">
                      <div className={cn("flex size-10 items-center justify-center rounded-full transition-all", s.circle)}>
                        <Icon className="size-[18px]" />
                      </div>
                      <p className={cn("mt-2 whitespace-nowrap text-xs", s.label)}>{step.label}</p>
                    </div>
                    {!isLast && <div className={cn("-mt-5 mx-3 h-0.5 flex-1 rounded-full", s.connector)} />}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right column — Insights */}
        <div className="space-y-4">
          {/* Clarus insights */}
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="mb-4 flex items-center gap-2">
              <div className="flex size-7 items-center justify-center rounded-lg bg-warning/10">
                <Lightbulb className="size-4 text-warning" />
              </div>
              <div>
                <h3 className="text-sm font-semibold">Clarus Insights</h3>
                <p className="text-[11px] text-muted-foreground">Automation intelligence</p>
              </div>
            </div>
            <div className="space-y-2.5">
              {INSIGHTS.map((ins, i) => {
                const Icon = insightIcons[ins.type];
                return (
                  <div key={i} className={cn("rounded-r-lg border-l-[3px] bg-muted/40 p-3", insightBorder[ins.priority])}>
                    <div className="flex items-start gap-2">
                      <Icon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                      <div>
                        <p className="text-xs font-semibold">{ins.title}</p>
                        <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{ins.description}</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Recent activity */}
          <div className="rounded-xl border border-border bg-card p-4">
            <h3 className="mb-3 text-sm font-semibold">Recent Calls</h3>
            <div className="space-y-3">
              {[
                { patient: "James T.", outcome: "Booked", time: "9:45 AM", status: "success" as const },
                { patient: "Maria L.", outcome: "Rescheduled", time: "9:12 AM", status: "warning" as const },
                { patient: "Robert K.", outcome: "No Answer", time: "8:30 AM", status: "muted" as const },
              ].map((call, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="flex size-8 items-center justify-center rounded-full bg-muted text-xs font-semibold">
                      {call.patient.split(" ").map((n) => n[0]).join("")}
                    </div>
                    <div>
                      <p className="text-sm font-medium">{call.patient}</p>
                      <p className="text-[11px] text-muted-foreground">{call.time}</p>
                    </div>
                  </div>
                  <span className={cn(
                    "rounded-full px-2 py-0.5 text-[11px] font-medium",
                    call.status === "success" && "bg-success/10 text-success",
                    call.status === "warning" && "bg-warning/10 text-warning",
                    call.status === "muted" && "bg-muted text-muted-foreground",
                  )}>
                    {call.outcome}
                  </span>
                </div>
              ))}
            </div>
            <Link href="/calls" className="mt-3 flex items-center gap-1 text-xs font-medium text-primary hover:underline">
              View all calls
              <ArrowRight className="size-3" />
            </Link>
          </div>

          {/* Upcoming appointments */}
          <div className="rounded-xl border border-border bg-card p-4">
            <h3 className="mb-3 text-sm font-semibold">Upcoming Appointments</h3>
            <div className="space-y-3">
              {[
                { patient: "James Thompson", type: "Follow-up", date: "Mar 10", time: "10:00 AM" },
                { patient: "Maria Lopez", type: "Blood Work Review", date: "Mar 10", time: "2:30 PM" },
                { patient: "Sarah Chen", type: "Annual Checkup", date: "Mar 11", time: "9:00 AM" },
              ].map((apt, i) => (
                <div key={i} className="flex items-start gap-3">
                  <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Calendar className="size-4" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{apt.patient}</p>
                    <p className="text-[11px] text-muted-foreground">{apt.type} — {apt.date}, {apt.time}</p>
                  </div>
                </div>
              ))}
            </div>
            <Link href="/appointments" className="mt-3 flex items-center gap-1 text-xs font-medium text-primary hover:underline">
              View schedule
              <ArrowRight className="size-3" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function InfoItem({ icon: Icon, label, value }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string }) {
  return (
    <div className="flex items-start gap-2">
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <div>
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="text-sm font-medium">{value}</p>
      </div>
    </div>
  );
}
