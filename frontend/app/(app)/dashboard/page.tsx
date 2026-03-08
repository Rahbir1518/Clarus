"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import {
  listPatients,
  createPatient,
  listWorkflows,
  listCallLogs,
  listConditions,
  pdfIntake,
} from "@/services/api";

import Link from "next/link";
import { useRouter } from "next/navigation";
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
  ArrowRight,
  Lightbulb,
  User,
  Activity,
  ArrowUpRight,
  UserPlus,
  X,
  Workflow,
  Users,
  FileText,
  Shield,
  Stethoscope,
  Hash,
  ClipboardCheck,
  AlertCircle,
  Upload,
  Loader2,
} from "lucide-react";

export default function DashboardPage() {
  const [patients, setPatients] = useState<any[]>([]);
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [showAddPatient, setShowAddPatient] = useState(false);
  const [patientName, setPatientName] = useState("");
  const [patientPhone, setPatientPhone] = useState("");
  const [savingPatient, setSavingPatient] = useState(false);

  const [workflows, setWorkflows] = useState<any[]>([]);
  const [callLogs, setCallLogs] = useState<any[]>([]);
  const [loadingData, setLoadingData] = useState(true);

  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [selectedConditions, setSelectedConditions] = useState<any[]>([]);
  const [loadingConditions, setLoadingConditions] = useState(false);
  const [uploadingPdf, setUploadingPdf] = useState(false);

  const router = useRouter();
  const { user } = useAuth0();
  const doctorId = user?.sub;

  const fetchPatients = useCallback(async () => {
    if (!doctorId) return;
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

  const fetchDashboardData = useCallback(async () => {
    if (!doctorId) return;
    setLoadingData(true);
    try {
      const [wfData, clData] = await Promise.all([
        listWorkflows(doctorId).catch(() => []),
        listCallLogs(undefined, doctorId).catch(() => []),
      ]);
      setWorkflows(Array.isArray(wfData) ? wfData : []);
      setCallLogs(Array.isArray(clData) ? clData : []);
    } catch {
      setWorkflows([]);
      setCallLogs([]);
    } finally {
      setLoadingData(false);
    }
  }, [doctorId]);

  useEffect(() => {
    fetchPatients();
    fetchDashboardData();
  }, [fetchPatients, fetchDashboardData]);

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

  const handleSelectPatient = useCallback(async (pid: string) => {
    if (selectedPatientId === pid) {
      setSelectedPatientId(null);
      setSelectedConditions([]);
      return;
    }
    setSelectedPatientId(pid);
    setLoadingConditions(true);
    try {
      const conds = await listConditions(pid);
      setSelectedConditions(Array.isArray(conds) ? conds : []);
    } catch {
      setSelectedConditions([]);
    } finally {
      setLoadingConditions(false);
    }
  }, [selectedPatientId]);

  const handlePdfIntake = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !doctorId) return;
    setUploadingPdf(true);
    try {
      const result = await pdfIntake(file, doctorId);
      if (result.patient?.id) {
        sessionStorage.setItem("pdfImportResult", JSON.stringify(result));
        router.push(`/patients/${result.patient.id}`);
      }
      fetchPatients();
    } catch (err: any) {
      alert(err.message || "PDF import failed");
    } finally {
      setUploadingPdf(false);
      e.target.value = "";
    }
  }, [doctorId, fetchPatients, router]);

  const today = new Date().toDateString();
  const callsToday = callLogs.filter(
    (cl) => new Date(cl.created_at).toDateString() === today
  );
  const confirmedToday = callsToday.filter((cl) => cl.status === "completed");
  const enabledWorkflows = workflows.filter((w) => w.status === "ENABLED");
  const answerRate =
    callsToday.length > 0
      ? Math.round((confirmedToday.length / callsToday.length) * 100)
      : 0;

  const stats = [
    { label: "Calls Today", value: String(callsToday.length), icon: Phone },
    { label: "Completed", value: String(confirmedToday.length), icon: CheckCircle2 },
    { label: "Answer Rate", value: callsToday.length > 0 ? `${answerRate}%` : "—", icon: TrendingUp },
    { label: "Active Workflows", value: String(enabledWorkflows.length), icon: Zap },
  ];

  const selectedPatient = patients.find((p) => p.id === selectedPatientId);
  const patientCallLogs = selectedPatientId
    ? callLogs.filter((cl) => cl.patient_id === selectedPatientId)
    : [];
  const totalRaf = selectedConditions.reduce((sum: number, c: any) => sum + (parseFloat(c.raf_impact) || 0), 0);
  const reviewNeeded = selectedConditions.filter((c) => c.status !== "documented");

  const recentCalls = callLogs.slice(0, 5);
  const recentWorkflows = workflows.slice(0, 5);

  const statusColor = (s: string) => {
    if (s === "completed") return "bg-success/10 text-success";
    if (s === "running") return "bg-primary/10 text-primary";
    if (s === "failed") return "bg-destructive/10 text-destructive";
    return "bg-muted text-muted-foreground";
  };

  const wfStatusColor = (s: string) => {
    if (s === "ENABLED") return "bg-success/10 text-success";
    return "bg-muted text-muted-foreground";
  };

  const conditionStatusConfig: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; color: string }> = {
    documented: { label: "Documented", icon: ClipboardCheck, color: "text-success" },
    review_needed: { label: "Review Needed", icon: AlertCircle, color: "text-warning" },
    pending_review: { label: "Pending Review", icon: Clock, color: "text-muted-foreground" },
  };

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
          <label className="cursor-pointer">
            <input type="file" accept=".pdf" className="hidden" onChange={handlePdfIntake} disabled={uploadingPdf} />
            <span className={cn(
              "inline-flex items-center gap-2 rounded-lg border border-border bg-background px-4 py-2 text-sm font-medium transition-colors",
              uploadingPdf ? "opacity-60 cursor-wait" : "hover:bg-muted"
            )}>
              {uploadingPdf ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
              {uploadingPdf ? "Processing…" : "Import from PDF"}
            </span>
          </label>
          <Button variant="outline" onClick={() => setShowAddPatient(true)}>
            <UserPlus className="size-4" />
            Add Patient
          </Button>
          <Link href="/workflow">
            <Button>
              <Activity className="size-4" />
              Open Workflow Builder
            </Button>
          </Link>
        </div>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center justify-between">
              <s.icon className="size-4 text-muted-foreground" />
            </div>
            <p className="mt-2 text-2xl font-bold">{loadingData ? "…" : s.value}</p>
            <p className="text-xs text-muted-foreground">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Patient selector + EHR detail */}
      <div className="rounded-xl border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div className="flex items-center gap-2">
            <Users className="size-4 text-primary" />
            <div>
              <h3 className="text-sm font-semibold">Patients</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {loadingPatients
                  ? "Loading…"
                  : `${patients.length} patient${patients.length !== 1 ? "s" : ""} — click to view details`}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => setShowAddPatient(true)}>
              <UserPlus className="size-3.5" />
              Add Patient
            </Button>
            <Link href="/patients">
              <Button size="sm" variant="ghost">
                View All <ArrowRight className="size-3" />
              </Button>
            </Link>
          </div>
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
                  {["Patient", "Phone", "Insurance", "Risk", ""].map((h) => (
                    <th key={h} className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {patients.slice(0, 8).map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => handleSelectPatient(p.id)}
                    className={cn(
                      "border-b border-border/50 last:border-0 cursor-pointer transition-colors",
                      selectedPatientId === p.id ? "bg-primary/5 hover:bg-primary/10" : "hover:bg-muted/30"
                    )}
                  >
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "flex size-8 items-center justify-center rounded-full text-xs font-semibold",
                          selectedPatientId === p.id ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary"
                        )}>
                          {p.name?.split(" ").map((n: string) => n[0]).join("").slice(0, 2).toUpperCase() || "?"}
                        </div>
                        <div>
                          <span className="font-medium">{p.name}</span>
                          {p.dob && <p className="text-[10px] text-muted-foreground">DOB: {p.dob}</p>}
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-muted-foreground">{p.phone}</td>
                    <td className="px-5 py-3 text-muted-foreground text-xs">{p.insurance || "—"}</td>
                    <td className="px-5 py-3">
                      {p.risk_level && p.risk_level !== "low" ? (
                        <span className={cn(
                          "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold",
                          p.risk_level === "high" ? "bg-destructive/10 text-destructive" : "bg-warning/10 text-warning"
                        )}>
                          <AlertTriangle className="size-3" />
                          {p.risk_level.charAt(0).toUpperCase() + p.risk_level.slice(1)}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">Low</span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <Link href={`/patients/${p.id}`} onClick={(e) => e.stopPropagation()}>
                        <Button size="sm" variant="ghost">
                          Full Profile <ArrowRight className="size-3" />
                        </Button>
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {patients.length > 8 && (
              <div className="px-5 py-3 border-t border-border">
                <Link href="/patients" className="text-xs font-medium text-primary hover:underline">
                  View all {patients.length} patients →
                </Link>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Selected patient EHR detail */}
      {selectedPatient && (
        <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
          {/* Left: Patient profile + conditions */}
          <div className="space-y-6">
            {/* Patient profile header */}
            <div className="rounded-xl border border-primary/20 bg-card p-5">
              <div className="flex items-start gap-4">
                <div className={cn(
                  "flex size-14 shrink-0 items-center justify-center rounded-full text-lg font-bold text-primary-foreground",
                  selectedPatient.risk_level === "high" ? "bg-destructive" : selectedPatient.risk_level === "moderate" ? "bg-warning" : "bg-primary"
                )}>
                  {selectedPatient.name?.split(" ").map((n: string) => n[0]).join("").slice(0, 2).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-3">
                    <h2 className="text-xl font-bold">{selectedPatient.name}</h2>
                    {selectedPatient.risk_level && selectedPatient.risk_level !== "low" && (
                      <span className={cn(
                        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold",
                        selectedPatient.risk_level === "high" ? "bg-destructive/10 text-destructive" : "bg-warning/10 text-warning"
                      )}>
                        <AlertTriangle className="size-3" />
                        {selectedPatient.risk_level.charAt(0).toUpperCase() + selectedPatient.risk_level.slice(1)} Risk
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground mt-0.5">
                    {selectedPatient.dob && `DOB: ${selectedPatient.dob}`}
                    {selectedPatient.dob && selectedPatient.mrn && " · "}
                    {selectedPatient.mrn && `MRN: ${selectedPatient.mrn}`}
                    {(selectedPatient.dob || selectedPatient.mrn) && selectedPatient.insurance && " · "}
                    {selectedPatient.insurance}
                  </p>
                  <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2.5 lg:grid-cols-4">
                    <InfoItem icon={Phone} label="Phone" value={selectedPatient.phone} />
                    <InfoItem icon={Calendar} label="Last Visit" value={selectedPatient.last_visit || "—"} />
                    <InfoItem icon={Stethoscope} label="Physician" value={selectedPatient.primary_physician || "—"} />
                    <InfoItem icon={Shield} label="Insurance" value={selectedPatient.insurance || "—"} />
                  </div>
                </div>
                <div className="hidden lg:flex items-center gap-3 shrink-0">
                  <div className="text-center px-3 py-2 rounded-lg border border-border bg-muted/30">
                    <p className="text-lg font-bold font-mono text-primary">{totalRaf.toFixed(3)}</p>
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Current RAF</p>
                  </div>
                  <div className="text-center px-3 py-2 rounded-lg border border-border bg-muted/30">
                    <p className="text-lg font-bold font-mono">{selectedConditions.length}</p>
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Conditions</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Active Problem / Condition List */}
            <div className="rounded-xl border border-border bg-card">
              <div className="flex items-center justify-between border-b border-border px-5 py-4">
                <div>
                  <h3 className="text-sm font-semibold">Active Problem / Condition List</h3>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {loadingConditions ? "Loading…" : `${selectedConditions.length} active condition${selectedConditions.length !== 1 ? "s" : ""}`}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground">ICD-10 / HCC</span>
                  <Link href={`/patients/${selectedPatientId}`}>
                    <Button size="sm" variant="outline">
                      Manage Conditions <ArrowRight className="size-3" />
                    </Button>
                  </Link>
                </div>
              </div>
              {loadingConditions ? (
                <div className="px-5 py-6 text-sm text-muted-foreground">Loading conditions…</div>
              ) : selectedConditions.length === 0 ? (
                <div className="px-5 py-6 text-center text-sm text-muted-foreground">
                  No conditions recorded.{" "}
                  <Link href={`/patients/${selectedPatientId}`} className="text-primary hover:underline">
                    Add conditions
                  </Link>{" "}
                  to this patient&apos;s profile.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        {["ICD-10", "Condition", "HCC", "RAF Impact", "Status"].map((h) => (
                          <th key={h} className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {selectedConditions.map((c) => {
                        const st = conditionStatusConfig[c.status] || conditionStatusConfig.documented;
                        const StIcon = st.icon;
                        const rafVal = parseFloat(c.raf_impact) || 0;
                        return (
                          <tr key={c.id} className="border-b border-border/50 last:border-0 hover:bg-muted/30 transition-colors">
                            <td className="px-5 py-3">
                              <code className="rounded bg-muted px-2 py-0.5 font-mono text-xs">{c.icd10_code}</code>
                            </td>
                            <td className="px-5 py-3 font-medium">{c.description}</td>
                            <td className="px-5 py-3">
                              {c.hcc_category ? (
                                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">{c.hcc_category}</span>
                              ) : "—"}
                            </td>
                            <td className="px-5 py-3">
                              <span className={cn(
                                "text-sm font-semibold",
                                rafVal > 0 ? "text-success" : rafVal < 0 ? "text-destructive" : "text-muted-foreground"
                              )}>
                                {rafVal > 0 ? "+" : ""}{rafVal.toFixed(3)}
                              </span>
                            </td>
                            <td className="px-5 py-3">
                              <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", st.color)}>
                                <StIcon className="size-3.5" />
                                {st.label}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>

          {/* Right: Beacon Insights + RAF + stepper */}
          <div className="space-y-4">
            <div className="rounded-xl border border-primary/20 bg-card p-4">
              <div className="mb-4 flex items-center gap-2">
                <div className="flex size-7 items-center justify-center rounded-lg bg-primary/10">
                  <Lightbulb className="size-4 text-primary" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold">Beacon AI Insights</h3>
                  <p className="text-[11px] text-muted-foreground">{reviewNeeded.length} gap{reviewNeeded.length !== 1 ? "s" : ""} identified</p>
                </div>
              </div>
              <div className="space-y-2.5">
                {reviewNeeded.length > 0 ? (
                  reviewNeeded.map((c) => (
                    <div key={c.id} className="rounded-r-lg border-l-[3px] border-l-warning bg-muted/40 p-3">
                      <div className="flex items-start gap-2">
                        <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-warning" />
                        <div>
                          <p className="text-xs font-semibold">{c.description}</p>
                          <p className="mt-0.5 text-[11px] text-muted-foreground">
                            {c.icd10_code} · {c.hcc_category || "No HCC"} · {conditionStatusConfig[c.status]?.label || c.status}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))
                ) : selectedConditions.length > 0 ? (
                  <div className="rounded-r-lg border-l-[3px] border-l-success bg-muted/40 p-3">
                    <div className="flex items-start gap-2">
                      <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-success" />
                      <div>
                        <p className="text-xs font-semibold">All Conditions Documented</p>
                        <p className="mt-0.5 text-[11px] text-muted-foreground">No gaps identified.</p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">Select a patient and add conditions to see insights.</p>
                )}
                {patientCallLogs.filter((l) => l.status === "failed").length > 0 && (
                  <div className="rounded-r-lg border-l-[3px] border-l-destructive bg-muted/40 p-3">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
                      <div>
                        <p className="text-xs font-semibold">{patientCallLogs.filter((l) => l.status === "failed").length} Failed Call(s)</p>
                        <p className="mt-0.5 text-[11px] text-muted-foreground">Check call log for details.</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* RAF Summary */}
            <div className="rounded-xl border border-border bg-card p-4">
              <h3 className="text-sm font-semibold mb-3">RAF Summary</h3>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Current RAF</span>
                  <span className="text-lg font-bold font-mono text-primary">{totalRaf.toFixed(3)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Active Conditions</span>
                  <span className="text-sm font-semibold">{selectedConditions.length}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Review Needed</span>
                  <span className={cn("text-sm font-semibold", reviewNeeded.length > 0 ? "text-warning" : "text-success")}>{reviewNeeded.length}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Patient Calls</span>
                  <span className="text-sm font-semibold">{patientCallLogs.length}</span>
                </div>
              </div>
            </div>

            {/* Workflow Progress Stepper */}
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold">Workflow Progress</h3>
                <Link href={`/patients/${selectedPatientId}`}>
                  <Button size="sm" variant="ghost" className="text-[10px] h-6 px-2">View Profile</Button>
                </Link>
              </div>
              <WorkflowStepper steps={[
                { label: "Review Patient", done: !!selectedPatient.dob || !!selectedPatient.insurance },
                { label: "Identify Gaps", done: selectedConditions.length > 0 },
                { label: "Add HCC Codes", done: selectedConditions.some((c: any) => c.hcc_category) },
                { label: "Submit & Log", done: patientCallLogs.some((l: any) => l.status === "completed") },
              ]} />
            </div>
          </div>
        </div>
      )}

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

      {/* Bottom section: Workflows + Call Logs + Quick Links */}
      <div className="grid gap-6 xl:grid-cols-[1fr_1fr_320px]">
        {/* Workflows */}
        <div className="rounded-xl border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <div className="flex items-center gap-2">
              <Workflow className="size-4 text-primary" />
              <h3 className="text-sm font-semibold">Workflows</h3>
            </div>
            <Link href="/workflow"><Button size="sm" variant="ghost"><Zap className="size-3" /> Open Builder</Button></Link>
          </div>
          {loadingData ? (
            <div className="px-5 py-6 text-sm text-muted-foreground">Loading…</div>
          ) : workflows.length === 0 ? (
            <div className="px-5 py-6 text-center text-sm text-muted-foreground">No workflows yet.</div>
          ) : (
            <div className="divide-y divide-border/50">
              {recentWorkflows.map((wf) => (
                <div key={wf.id} className="flex items-center justify-between px-5 py-3 hover:bg-muted/30 transition-colors">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h4 className="text-xs font-medium truncate">{wf.name}</h4>
                      <span className={cn("inline-flex rounded-full px-1.5 py-0.5 text-[9px] font-semibold", wfStatusColor(wf.status))}>{wf.status}</span>
                    </div>
                    <span className="text-[10px] text-muted-foreground">{Array.isArray(wf.nodes) ? wf.nodes.length : 0} nodes</span>
                  </div>
                  <Link href={`/workflow?id=${wf.id}`}><Button size="sm" variant="ghost"><ArrowRight className="size-3" /></Button></Link>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent Call Logs */}
        <div className="rounded-xl border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <div className="flex items-center gap-2">
              <Phone className="size-4 text-primary" />
              <h3 className="text-sm font-semibold">Recent Calls</h3>
            </div>
            <Link href="/calls"><Button size="sm" variant="ghost">All <ArrowRight className="size-3" /></Button></Link>
          </div>
          {loadingData ? (
            <div className="px-5 py-6 text-sm text-muted-foreground">Loading…</div>
          ) : callLogs.length === 0 ? (
            <div className="px-5 py-6 text-center text-sm text-muted-foreground">No call logs yet.</div>
          ) : (
            <div className="divide-y divide-border/50">
              {recentCalls.map((cl) => (
                <div key={cl.id} className="flex items-center justify-between px-5 py-3 hover:bg-muted/30 transition-colors">
                  <div className="flex items-center gap-2">
                    <span className={cn("inline-flex rounded-full px-1.5 py-0.5 text-[9px] font-semibold capitalize", statusColor(cl.status))}>{cl.status}</span>
                    {cl.outcome && <span className="text-[10px] text-muted-foreground">{cl.outcome}</span>}
                  </div>
                  <span className="text-[10px] text-muted-foreground">{new Date(cl.created_at).toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Quick links */}
        <div className="rounded-xl border border-border bg-card p-4">
          <h3 className="mb-3 text-sm font-semibold">Quick Links</h3>
          <div className="space-y-2">
            <Link href="/workflow" className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm hover:bg-muted/50 transition-colors">
              <Activity className="size-4 text-primary" /><span>Workflow Builder</span><ArrowUpRight className="size-3 ml-auto text-muted-foreground" />
            </Link>
            <Link href="/patients" className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm hover:bg-muted/50 transition-colors">
              <User className="size-4 text-primary" /><span>Patient Directory</span><ArrowUpRight className="size-3 ml-auto text-muted-foreground" />
            </Link>
            <Link href="/calls" className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm hover:bg-muted/50 transition-colors">
              <FileText className="size-4 text-primary" /><span>Call Logs</span><ArrowUpRight className="size-3 ml-auto text-muted-foreground" />
            </Link>
            <Link href="/audit-log" className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm hover:bg-muted/50 transition-colors">
              <Clock className="size-4 text-primary" /><span>Audit Log</span><ArrowUpRight className="size-3 ml-auto text-muted-foreground" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

function InsightItem({ icon: Icon, title, description, border }: { icon: React.ComponentType<{ className?: string }>; title: string; description: string; border: string }) {
  return (
    <div className={cn("rounded-r-lg border-l-[3px] bg-muted/40 p-3", border)}>
      <div className="flex items-start gap-2">
        <Icon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
        <div>
          <p className="text-xs font-semibold">{title}</p>
          <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{description}</p>
        </div>
      </div>
    </div>
  );
}

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

function WorkflowStepper({ steps }: { steps: { label: string; done: boolean }[] }) {
  const activeIdx = steps.findIndex((s) => !s.done);
  return (
    <div className="space-y-0">
      {steps.map((step, idx) => {
        const isActive = idx === activeIdx;
        const isDone = step.done;
        return (
          <div key={idx} className="flex items-center gap-3 py-2">
            <div className={cn(
              "flex size-7 items-center justify-center rounded-full text-xs font-bold shrink-0 transition-all",
              isDone ? "bg-primary text-primary-foreground" :
              isActive ? "bg-card border-2 border-primary text-primary ring-4 ring-primary/10" :
              "bg-muted text-muted-foreground border border-border"
            )}>
              {isDone ? <CheckCircle2 className="size-4" /> : idx + 1}
            </div>
            <span className={cn("text-xs", isDone ? "text-primary font-semibold" : isActive ? "text-primary font-semibold" : "text-muted-foreground")}>
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
