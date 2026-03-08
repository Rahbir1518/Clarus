"use client";

import { useState, useEffect, useCallback, use } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import {
  getPatient,
  updatePatient,
  listConditions,
  createCondition,
  updateCondition,
  deleteCondition,
  listCallLogs,
  listMedications,
  createMedication,
  updateMedication,
  deleteMedication,
} from "@/services/api";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  ArrowLeft,
  Calendar,
  Phone,
  Shield,
  Stethoscope,
  User,
  Hash,
  AlertTriangle,
  ClipboardCheck,
  AlertCircle,
  Clock,
  Plus,
  Trash2,
  Edit3,
  Save,
  X,
  Activity,
  Lightbulb,
  CheckCircle2,
  FileText,
  Pill,
} from "lucide-react";

const riskStyles: Record<string, string> = {
  high: "bg-destructive/10 text-destructive",
  moderate: "bg-warning/10 text-warning",
  low: "bg-success/10 text-success",
};

const conditionStatusConfig: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; color: string }> = {
  documented: { label: "Documented", icon: ClipboardCheck, color: "text-success" },
  review_needed: { label: "Review Needed", icon: AlertCircle, color: "text-warning" },
  pending_review: { label: "Pending Review", icon: Clock, color: "text-muted-foreground" },
};

export default function PatientDetailPage({
  params,
}: {
  params: Promise<{ patientId: string }>;
}) {
  const { patientId } = use(params);
  const { user } = useAuth0();

  const [patient, setPatient] = useState<any>(null);
  const [conditions, setConditions] = useState<any[]>([]);
  const [callLogs, setCallLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingProfile, setEditingProfile] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);

  const [profileForm, setProfileForm] = useState({
    name: "", phone: "", dob: "", mrn: "", insurance: "",
    primary_physician: "", last_visit: "", risk_level: "low", notes: "",
  });

  const [medications, setMedications] = useState<any[]>([]);

  const [showAddCondition, setShowAddCondition] = useState(false);
  const [conditionForm, setConditionForm] = useState({
    icd10_code: "", description: "", hcc_category: "", raf_impact: "0", status: "documented",
  });
  const [savingCondition, setSavingCondition] = useState(false);
  const [editingConditionId, setEditingConditionId] = useState<string | null>(null);

  const [showAddMedication, setShowAddMedication] = useState(false);
  const [medicationForm, setMedicationForm] = useState({
    name: "", dosage: "", frequency: "", route: "", prescriber: "",
    start_date: "", end_date: "", status: "active", notes: "",
  });
  const [savingMedication, setSavingMedication] = useState(false);
  const [editingMedicationId, setEditingMedicationId] = useState<string | null>(null);

  const [pdfImportResult, setPdfImportResult] = useState<any>(null);

  useEffect(() => {
    try {
      const stored = sessionStorage.getItem("pdfImportResult");
      if (stored) {
        setPdfImportResult(JSON.parse(stored));
        sessionStorage.removeItem("pdfImportResult");
      }
    } catch {}
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [p, conds, meds, logs] = await Promise.all([
        getPatient(patientId),
        listConditions(patientId).catch(() => []),
        listMedications(patientId).catch(() => []),
        listCallLogs(undefined, user?.sub).catch(() => []),
      ]);
      setPatient(p);
      setConditions(Array.isArray(conds) ? conds : []);
      setMedications(Array.isArray(meds) ? meds : []);
      const patientLogs = (Array.isArray(logs) ? logs : []).filter(
        (l: any) => l.patient_id === patientId
      );
      setCallLogs(patientLogs);
      setProfileForm({
        name: p.name || "",
        phone: p.phone || "",
        dob: p.dob || "",
        mrn: p.mrn || "",
        insurance: p.insurance || "",
        primary_physician: p.primary_physician || "",
        last_visit: p.last_visit || "",
        risk_level: p.risk_level || "low",
        notes: p.notes || "",
      });
    } catch {
      setPatient(null);
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSaveProfile = useCallback(async () => {
    setSavingProfile(true);
    try {
      const payload: Record<string, string | null> = {};
      for (const [k, v] of Object.entries(profileForm)) {
        if (v !== "" && v !== null) payload[k] = v;
        else if (k !== "name" && k !== "phone") payload[k] = null;
      }
      const updated = await updatePatient(patientId, payload);
      setPatient(updated);
      setEditingProfile(false);
    } catch { /* ignore */ }
    finally { setSavingProfile(false); }
  }, [patientId, profileForm]);

  const handleAddCondition = useCallback(async () => {
    if (!conditionForm.icd10_code.trim() || !conditionForm.description.trim()) return;
    setSavingCondition(true);
    try {
      const payload = {
        icd10_code: conditionForm.icd10_code.trim(),
        description: conditionForm.description.trim(),
        hcc_category: conditionForm.hcc_category.trim() || undefined,
        raf_impact: parseFloat(conditionForm.raf_impact) || 0,
        status: conditionForm.status,
      };

      if (editingConditionId) {
        await updateCondition(patientId, editingConditionId, payload);
      } else {
        await createCondition(patientId, payload);
      }

      setConditionForm({ icd10_code: "", description: "", hcc_category: "", raf_impact: "0", status: "documented" });
      setShowAddCondition(false);
      setEditingConditionId(null);
      const fresh = await listConditions(patientId);
      setConditions(Array.isArray(fresh) ? fresh : []);
    } catch { /* ignore */ }
    finally { setSavingCondition(false); }
  }, [patientId, conditionForm, editingConditionId]);

  const handleDeleteCondition = useCallback(async (condId: string) => {
    if (!confirm("Delete this condition?")) return;
    try {
      await deleteCondition(patientId, condId);
      setConditions((prev) => prev.filter((c) => c.id !== condId));
    } catch { /* ignore */ }
  }, [patientId]);

  const startEditCondition = useCallback((cond: any) => {
    setEditingConditionId(cond.id);
    setConditionForm({
      icd10_code: cond.icd10_code || "",
      description: cond.description || "",
      hcc_category: cond.hcc_category || "",
      raf_impact: String(cond.raf_impact ?? 0),
      status: cond.status || "documented",
    });
    setShowAddCondition(true);
  }, []);

  const handleAddMedication = useCallback(async () => {
    if (!medicationForm.name.trim()) return;
    setSavingMedication(true);
    try {
      const payload: Record<string, any> = { name: medicationForm.name.trim() };
      if (medicationForm.dosage.trim()) payload.dosage = medicationForm.dosage.trim();
      if (medicationForm.frequency.trim()) payload.frequency = medicationForm.frequency.trim();
      if (medicationForm.route.trim()) payload.route = medicationForm.route.trim();
      if (medicationForm.prescriber.trim()) payload.prescriber = medicationForm.prescriber.trim();
      if (medicationForm.start_date) payload.start_date = medicationForm.start_date;
      if (medicationForm.end_date) payload.end_date = medicationForm.end_date;
      payload.status = medicationForm.status;
      if (medicationForm.notes.trim()) payload.notes = medicationForm.notes.trim();

      if (editingMedicationId) {
        await updateMedication(patientId, editingMedicationId, payload);
      } else {
        await createMedication(patientId, payload as any);
      }

      setMedicationForm({ name: "", dosage: "", frequency: "", route: "", prescriber: "", start_date: "", end_date: "", status: "active", notes: "" });
      setShowAddMedication(false);
      setEditingMedicationId(null);
      const fresh = await listMedications(patientId);
      setMedications(Array.isArray(fresh) ? fresh : []);
    } catch { /* ignore */ }
    finally { setSavingMedication(false); }
  }, [patientId, medicationForm, editingMedicationId]);

  const handleDeleteMedication = useCallback(async (medId: string) => {
    if (!confirm("Delete this medication?")) return;
    try {
      await deleteMedication(patientId, medId);
      setMedications((prev) => prev.filter((m) => m.id !== medId));
    } catch { /* ignore */ }
  }, [patientId]);

  const startEditMedication = useCallback((med: any) => {
    setEditingMedicationId(med.id);
    setMedicationForm({
      name: med.name || "",
      dosage: med.dosage || "",
      frequency: med.frequency || "",
      route: med.route || "",
      prescriber: med.prescriber || "",
      start_date: med.start_date || "",
      end_date: med.end_date || "",
      status: med.status || "active",
      notes: med.notes || "",
    });
    setShowAddMedication(true);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-muted-foreground">Loading patient…</p>
      </div>
    );
  }

  if (!patient) {
    return (
      <div className="space-y-4">
        <Link href="/patients" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
          <ArrowLeft className="size-3.5" /> Back to Patients
        </Link>
        <p className="text-sm text-muted-foreground">Patient not found.</p>
      </div>
    );
  }

  const initials = patient.name
    ?.split(" ")
    .map((n: string) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase() || "?";

  const totalRaf = conditions.reduce((sum: number, c: any) => sum + (parseFloat(c.raf_impact) || 0), 0);
  const reviewNeeded = conditions.filter((c) => c.status !== "documented");
  const completedLogs = callLogs.filter((l) => l.status === "completed");
  const failedLogs = callLogs.filter((l) => l.status === "failed");

  return (
    <div className="space-y-6">
      {/* Back navigation */}
      <Link href="/patients" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
        <ArrowLeft className="size-3.5" /> Back to Patients
      </Link>

      {/* Patient profile header */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-start gap-4">
          <div className={cn(
            "flex size-16 shrink-0 items-center justify-center rounded-full text-lg font-bold text-primary-foreground",
            patient.risk_level === "high" ? "bg-destructive" : patient.risk_level === "moderate" ? "bg-warning" : "bg-primary"
          )}>
            {initials}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-xl font-bold">{patient.name}</h1>
              {patient.risk_level && patient.risk_level !== "low" && (
                <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold", riskStyles[patient.risk_level] || riskStyles.low)}>
                  <AlertTriangle className="size-3" />
                  {patient.risk_level.charAt(0).toUpperCase() + patient.risk_level.slice(1)} Risk
                </span>
              )}
              <Button size="sm" variant="ghost" onClick={() => setEditingProfile(!editingProfile)}>
                <Edit3 className="size-3.5" />
                {editingProfile ? "Cancel" : "Edit Profile"}
              </Button>
            </div>
            <p className="text-sm text-muted-foreground mt-0.5">
              {patient.dob && `DOB: ${patient.dob}`}
              {patient.dob && patient.mrn && " · "}
              {patient.mrn && `MRN: ${patient.mrn}`}
              {(patient.dob || patient.mrn) && patient.insurance && " · "}
              {patient.insurance && patient.insurance}
            </p>

            {!editingProfile && (
              <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 lg:grid-cols-4">
                <InfoItem icon={Phone} label="Phone" value={patient.phone} />
                <InfoItem icon={Calendar} label="Last Visit" value={patient.last_visit || "—"} />
                <InfoItem icon={Stethoscope} label="Primary Physician" value={patient.primary_physician || "—"} />
                <InfoItem icon={Shield} label="Insurance" value={patient.insurance || "—"} />
              </div>
            )}
          </div>

          {/* Key metrics */}
          <div className="hidden lg:flex items-center gap-4 shrink-0">
            <MetricCard label="Current RAF" value={totalRaf.toFixed(3)} />
            <MetricCard label="Conditions" value={String(conditions.length)} />
            <MetricCard label="Medications" value={String(medications.length)} />
            <MetricCard label="Calls" value={String(callLogs.length)} />
          </div>
        </div>

        {/* Edit profile form */}
        {editingProfile && (
          <div className="mt-5 border-t border-border pt-5">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <FormField label="Full Name" value={profileForm.name} onChange={(v) => setProfileForm((f) => ({ ...f, name: v }))} />
              <FormField label="Phone" value={profileForm.phone} onChange={(v) => setProfileForm((f) => ({ ...f, phone: v }))} />
              <FormField label="Date of Birth" value={profileForm.dob} onChange={(v) => setProfileForm((f) => ({ ...f, dob: v }))} type="date" />
              <FormField label="MRN" value={profileForm.mrn} onChange={(v) => setProfileForm((f) => ({ ...f, mrn: v }))} placeholder="e.g. MRN-2024-0847" />
              <FormField label="Insurance" value={profileForm.insurance} onChange={(v) => setProfileForm((f) => ({ ...f, insurance: v }))} placeholder="e.g. Blue Cross Blue Shield" />
              <FormField label="Primary Physician" value={profileForm.primary_physician} onChange={(v) => setProfileForm((f) => ({ ...f, primary_physician: v }))} placeholder="e.g. Dr. Smith" />
              <FormField label="Last Visit" value={profileForm.last_visit} onChange={(v) => setProfileForm((f) => ({ ...f, last_visit: v }))} type="date" />
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Risk Level</label>
                <select
                  value={profileForm.risk_level}
                  onChange={(e) => setProfileForm((f) => ({ ...f, risk_level: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="low">Low</option>
                  <option value="moderate">Moderate</option>
                  <option value="high">High</option>
                </select>
              </div>
              <div className="sm:col-span-2 lg:col-span-3">
                <label className="block text-xs font-medium text-muted-foreground mb-1">Notes</label>
                <textarea
                  value={profileForm.notes}
                  onChange={(e) => setProfileForm((f) => ({ ...f, notes: e.target.value }))}
                  rows={2}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary resize-none"
                  placeholder="Clinical notes…"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="outline" size="sm" onClick={() => setEditingProfile(false)}>Cancel</Button>
              <Button size="sm" disabled={savingProfile} onClick={handleSaveProfile}>
                <Save className="size-3.5" />
                {savingProfile ? "Saving…" : "Save Profile"}
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* PDF import result */}
      {pdfImportResult && !pdfImportResult.error && (
        <div className="rounded-xl border border-success/30 bg-success/5 p-5">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="size-4 text-success" />
                <p className="text-sm font-semibold text-success">Patient created from PDF</p>
              </div>
              <button onClick={() => setPdfImportResult(null)} className="text-xs text-muted-foreground hover:text-foreground underline">Dismiss</button>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {pdfImportResult.patient?.name && (
                <div className="rounded-lg bg-card border border-border p-3">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Name</p>
                  <p className="text-sm font-semibold">{pdfImportResult.patient.name}</p>
                </div>
              )}
              {pdfImportResult.patient?.dob && (
                <div className="rounded-lg bg-card border border-border p-3">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Date of Birth</p>
                  <p className="text-sm font-semibold">{pdfImportResult.patient.dob}</p>
                </div>
              )}
              {pdfImportResult.patient?.mrn && (
                <div className="rounded-lg bg-card border border-border p-3">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">MRN</p>
                  <p className="text-sm font-mono font-semibold">{pdfImportResult.patient.mrn}</p>
                </div>
              )}
              {pdfImportResult.patient?.insurance && (
                <div className="rounded-lg bg-card border border-border p-3">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Insurance</p>
                  <p className="text-sm font-semibold">{pdfImportResult.patient.insurance}</p>
                </div>
              )}
            </div>

            {pdfImportResult.created_medications > 0 && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Pill className="size-3.5" />
                <span>{pdfImportResult.created_medications} medication{pdfImportResult.created_medications !== 1 ? "s" : ""} added from PDF</span>
              </div>
            )}

            {pdfImportResult.extracted?.lab_results?.length > 0 && (
              <div>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-2">
                  Extracted Lab Results ({pdfImportResult.extracted.lab_results.length})
                </p>
                <div className="overflow-x-auto rounded-lg border border-border bg-card">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left px-3 py-2 font-semibold">Test</th>
                        <th className="text-left px-3 py-2 font-semibold">Value</th>
                        <th className="text-left px-3 py-2 font-semibold">Unit</th>
                        <th className="text-left px-3 py-2 font-semibold">Ref Range</th>
                        <th className="text-left px-3 py-2 font-semibold">Flag</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pdfImportResult.extracted.lab_results.map((r: any, i: number) => (
                        <tr key={i} className="border-b border-border/30 last:border-0">
                          <td className="px-3 py-1.5">{r.test_name}</td>
                          <td className="px-3 py-1.5 font-mono">{r.value}</td>
                          <td className="px-3 py-1.5 text-muted-foreground">{r.unit}</td>
                          <td className="px-3 py-1.5 text-muted-foreground">{r.reference_range}</td>
                          <td className="px-3 py-1.5">
                            <span className={cn(
                              "rounded px-1.5 py-0.5 text-[10px] font-semibold",
                              r.flag === "high" ? "bg-destructive/10 text-destructive" :
                              r.flag === "low" ? "bg-warning/10 text-warning" :
                              "bg-success/10 text-success"
                            )}>
                              {r.flag}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Main layout */}
      <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
        {/* Left column */}
        <div className="space-y-6">
          {/* Active Problem / Condition List */}
          <div className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <h3 className="text-sm font-semibold">Active Problem / Condition List</h3>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {conditions.length} active condition{conditions.length !== 1 ? "s" : ""} on record
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground">ICD-10 / HCC</span>
                <Button size="sm" onClick={() => { setShowAddCondition(true); setEditingConditionId(null); setConditionForm({ icd10_code: "", description: "", hcc_category: "", raf_impact: "0", status: "documented" }); }}>
                  <Plus className="size-3.5" />
                  Add Condition
                </Button>
              </div>
            </div>

            {/* Add/Edit condition form */}
            {showAddCondition && (
              <div className="border-b border-border px-5 py-4 bg-muted/20">
                <h4 className="text-xs font-semibold mb-3">{editingConditionId ? "Edit Condition" : "Add New Condition"}</h4>
                <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                  <FormField label="ICD-10 Code *" value={conditionForm.icd10_code} onChange={(v) => setConditionForm((f) => ({ ...f, icd10_code: v }))} placeholder="e.g. E11.65" />
                  <div className="col-span-2 lg:col-span-2">
                    <FormField label="Description *" value={conditionForm.description} onChange={(v) => setConditionForm((f) => ({ ...f, description: v }))} placeholder="e.g. Type 2 Diabetes with Hyperglycemia" />
                  </div>
                  <FormField label="HCC Category" value={conditionForm.hcc_category} onChange={(v) => setConditionForm((f) => ({ ...f, hcc_category: v }))} placeholder="e.g. HCC 19" />
                  <FormField label="RAF Impact" value={conditionForm.raf_impact} onChange={(v) => setConditionForm((f) => ({ ...f, raf_impact: v }))} placeholder="e.g. 0.302" />
                </div>
                <div className="flex items-center gap-3 mt-3">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Status</label>
                    <select
                      value={conditionForm.status}
                      onChange={(e) => setConditionForm((f) => ({ ...f, status: e.target.value }))}
                      className="px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    >
                      <option value="documented">Documented</option>
                      <option value="review_needed">Review Needed</option>
                      <option value="pending_review">Pending Review</option>
                    </select>
                  </div>
                  <div className="flex items-end gap-2 ml-auto">
                    <Button variant="outline" size="sm" onClick={() => { setShowAddCondition(false); setEditingConditionId(null); }}>Cancel</Button>
                    <Button size="sm" disabled={savingCondition || !conditionForm.icd10_code.trim() || !conditionForm.description.trim()} onClick={handleAddCondition}>
                      {savingCondition ? "Saving…" : editingConditionId ? "Update" : "Add Condition"}
                    </Button>
                  </div>
                </div>
              </div>
            )}

            {conditions.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-muted-foreground">
                No conditions recorded. Add conditions to track the patient&apos;s active problems.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      {["ICD-10", "Condition", "HCC Category", "RAF Impact", "Status", ""].map((h) => (
                        <th key={h} className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {conditions.map((c) => {
                      const st = conditionStatusConfig[c.status] || conditionStatusConfig.documented;
                      const StIcon = st.icon;
                      const rafVal = parseFloat(c.raf_impact) || 0;
                      return (
                        <tr key={c.id} className="border-b border-border/50 last:border-0 transition-colors hover:bg-muted/30">
                          <td className="px-5 py-3">
                            <code className="rounded bg-muted px-2 py-0.5 font-mono text-xs">{c.icd10_code}</code>
                          </td>
                          <td className="px-5 py-3 font-medium">{c.description}</td>
                          <td className="px-5 py-3 text-muted-foreground">
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
                          <td className="px-5 py-3 text-right">
                            <div className="flex items-center gap-1 justify-end">
                              {c.status !== "documented" && (
                                <Button variant="ghost" size="sm" onClick={() => startEditCondition(c)}>Review</Button>
                              )}
                              <Button variant="ghost" size="sm" onClick={() => startEditCondition(c)}>
                                <Edit3 className="size-3" />
                              </Button>
                              <Button variant="ghost" size="sm" onClick={() => handleDeleteCondition(c.id)} className="text-destructive hover:text-destructive hover:bg-destructive/10">
                                <Trash2 className="size-3" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Medications */}
          <div className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <div className="flex items-center gap-2">
                  <Pill className="size-4 text-primary" />
                  <h3 className="text-sm font-semibold">Medications</h3>
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {medications.length} medication{medications.length !== 1 ? "s" : ""} on record
                </p>
              </div>
              <Button size="sm" onClick={() => { setShowAddMedication(true); setEditingMedicationId(null); setMedicationForm({ name: "", dosage: "", frequency: "", route: "", prescriber: "", start_date: "", end_date: "", status: "active", notes: "" }); }}>
                <Plus className="size-3.5" />
                Add Medication
              </Button>
            </div>

            {showAddMedication && (
              <div className="border-b border-border px-5 py-4 bg-muted/20">
                <h4 className="text-xs font-semibold mb-3">{editingMedicationId ? "Edit Medication" : "Add New Medication"}</h4>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                  <FormField label="Medication Name *" value={medicationForm.name} onChange={(v) => setMedicationForm((f) => ({ ...f, name: v }))} placeholder="e.g. Metformin" />
                  <FormField label="Dosage" value={medicationForm.dosage} onChange={(v) => setMedicationForm((f) => ({ ...f, dosage: v }))} placeholder="e.g. 500mg" />
                  <FormField label="Frequency" value={medicationForm.frequency} onChange={(v) => setMedicationForm((f) => ({ ...f, frequency: v }))} placeholder="e.g. Twice daily" />
                  <FormField label="Route" value={medicationForm.route} onChange={(v) => setMedicationForm((f) => ({ ...f, route: v }))} placeholder="e.g. Oral" />
                  <FormField label="Prescriber" value={medicationForm.prescriber} onChange={(v) => setMedicationForm((f) => ({ ...f, prescriber: v }))} placeholder="e.g. Dr. Smith" />
                  <FormField label="Start Date" value={medicationForm.start_date} onChange={(v) => setMedicationForm((f) => ({ ...f, start_date: v }))} type="date" />
                  <FormField label="End Date" value={medicationForm.end_date} onChange={(v) => setMedicationForm((f) => ({ ...f, end_date: v }))} type="date" />
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Status</label>
                    <select
                      value={medicationForm.status}
                      onChange={(e) => setMedicationForm((f) => ({ ...f, status: e.target.value }))}
                      className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    >
                      <option value="active">Active</option>
                      <option value="discontinued">Discontinued</option>
                      <option value="on_hold">On Hold</option>
                    </select>
                  </div>
                </div>
                <div className="mt-3">
                  <FormField label="Notes" value={medicationForm.notes} onChange={(v) => setMedicationForm((f) => ({ ...f, notes: v }))} placeholder="Additional notes…" />
                </div>
                <div className="flex items-end gap-2 mt-3 justify-end">
                  <Button variant="outline" size="sm" onClick={() => { setShowAddMedication(false); setEditingMedicationId(null); }}>Cancel</Button>
                  <Button size="sm" disabled={savingMedication || !medicationForm.name.trim()} onClick={handleAddMedication}>
                    {savingMedication ? "Saving…" : editingMedicationId ? "Update" : "Add Medication"}
                  </Button>
                </div>
              </div>
            )}

            {medications.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-muted-foreground">
                No medications recorded. Add medications to track the patient&apos;s prescriptions.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      {["Medication", "Dosage", "Frequency", "Route", "Prescriber", "Status", ""].map((h) => (
                        <th key={h} className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {medications.map((m) => {
                      const isActive = m.status === "active";
                      const isDiscontinued = m.status === "discontinued";
                      return (
                        <tr key={m.id} className={cn("border-b border-border/50 last:border-0 transition-colors hover:bg-muted/30", isDiscontinued && "opacity-60")}>
                          <td className="px-5 py-3">
                            <div>
                              <span className="font-medium">{m.name}</span>
                              {m.start_date && <p className="text-[10px] text-muted-foreground">Since {m.start_date}{m.end_date ? ` — ${m.end_date}` : ""}</p>}
                            </div>
                          </td>
                          <td className="px-5 py-3 text-muted-foreground">{m.dosage || "—"}</td>
                          <td className="px-5 py-3 text-muted-foreground">{m.frequency || "—"}</td>
                          <td className="px-5 py-3 text-muted-foreground">{m.route || "—"}</td>
                          <td className="px-5 py-3 text-muted-foreground">{m.prescriber || "—"}</td>
                          <td className="px-5 py-3">
                            <span className={cn(
                              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold",
                              isActive ? "bg-success/10 text-success" :
                              isDiscontinued ? "bg-muted text-muted-foreground" :
                              "bg-warning/10 text-warning"
                            )}>
                              {m.status === "on_hold" ? "On Hold" : m.status?.charAt(0).toUpperCase() + m.status?.slice(1)}
                            </span>
                          </td>
                          <td className="px-5 py-3 text-right">
                            <div className="flex items-center gap-1 justify-end">
                              <Button variant="ghost" size="sm" onClick={() => startEditMedication(m)}>
                                <Edit3 className="size-3" />
                              </Button>
                              <Button variant="ghost" size="sm" onClick={() => handleDeleteMedication(m.id)} className="text-destructive hover:text-destructive hover:bg-destructive/10">
                                <Trash2 className="size-3" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Patient call history */}
          <div className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div className="flex items-center gap-2">
                <Phone className="size-4 text-primary" />
                <div>
                  <h3 className="text-sm font-semibold">Call History</h3>
                  <p className="mt-0.5 text-xs text-muted-foreground">{callLogs.length} execution{callLogs.length !== 1 ? "s" : ""} for this patient</p>
                </div>
              </div>
            </div>
            {callLogs.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-muted-foreground">
                No call history for this patient yet.
              </div>
            ) : (
              <div className="divide-y divide-border/50">
                {callLogs.slice(0, 10).map((cl) => {
                  const execLog: any[] = Array.isArray(cl.execution_log) ? cl.execution_log : [];
                  return (
                    <div key={cl.id} className="px-5 py-3 hover:bg-muted/30 transition-colors">
                      <div className="flex items-center gap-2">
                        <span className={cn(
                          "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize",
                          cl.status === "completed" ? "bg-success/10 text-success" :
                          cl.status === "failed" ? "bg-destructive/10 text-destructive" :
                          "bg-muted text-muted-foreground"
                        )}>
                          {cl.status}
                        </span>
                        {cl.outcome && <span className="text-xs text-muted-foreground">{cl.outcome}</span>}
                        <span className="ml-auto text-[10px] text-muted-foreground">{new Date(cl.created_at).toLocaleString()}</span>
                      </div>
                      {execLog.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {execLog.map((step: any, i: number) => (
                            <span key={i} className="inline-flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-[10px]">
                              <span className="size-1.5 rounded-full" style={{
                                backgroundColor: step.status === "ok" ? "#10b981" : step.status === "error" ? "#ef4444" : "#6b7280"
                              }} />
                              {step.label || step.node_type}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right column — Insights */}
        <div className="space-y-4">
          {/* Clarus Insights */}
          <div className="rounded-xl border border-primary/20 bg-card p-4">
            <div className="mb-4 flex items-center gap-2">
              <div className="flex size-7 items-center justify-center rounded-lg bg-primary/10">
                <Lightbulb className="size-4 text-primary" />
              </div>
              <div>
                <h3 className="text-sm font-semibold">Clarus Insights</h3>
                <p className="text-[11px] text-muted-foreground">
                  {reviewNeeded.length} gap{reviewNeeded.length !== 1 ? "s" : ""} identified
                </p>
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
                          {c.icd10_code} · {c.hcc_category || "No HCC"} · Status: {conditionStatusConfig[c.status]?.label || c.status}
                        </p>
                      </div>
                    </div>
                  </div>
                ))
              ) : conditions.length > 0 ? (
                <div className="rounded-r-lg border-l-[3px] border-l-success bg-muted/40 p-3">
                  <div className="flex items-start gap-2">
                    <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-success" />
                    <div>
                      <p className="text-xs font-semibold">All Conditions Documented</p>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        All {conditions.length} conditions are fully documented.
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">Add conditions to see insights.</p>
              )}

              {failedLogs.length > 0 && (
                <div className="rounded-r-lg border-l-[3px] border-l-destructive bg-muted/40 p-3">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
                    <div>
                      <p className="text-xs font-semibold">{failedLogs.length} Failed Call{failedLogs.length !== 1 ? "s" : ""}</p>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        Review failed workflow executions in the call history below.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {completedLogs.length > 0 && (
                <div className="rounded-r-lg border-l-[3px] border-l-primary bg-muted/40 p-3">
                  <div className="flex items-start gap-2">
                    <Activity className="mt-0.5 size-3.5 shrink-0 text-primary" />
                    <div>
                      <p className="text-xs font-semibold">{completedLogs.length} Completed Call{completedLogs.length !== 1 ? "s" : ""}</p>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        Patient has {completedLogs.length} successful workflow execution{completedLogs.length !== 1 ? "s" : ""}.
                      </p>
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
                <span className="text-xs text-muted-foreground">Current RAF Score</span>
                <span className="text-lg font-bold font-mono text-primary">{totalRaf.toFixed(3)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Active Conditions</span>
                <span className="text-sm font-semibold">{conditions.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Review Needed</span>
                <span className={cn("text-sm font-semibold", reviewNeeded.length > 0 ? "text-warning" : "text-success")}>
                  {reviewNeeded.length}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Documented</span>
                <span className="text-sm font-semibold text-success">
                  {conditions.length - reviewNeeded.length}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Active Medications</span>
                <span className="text-sm font-semibold">{medications.filter((m) => m.status === "active").length}</span>
              </div>
            </div>
          </div>

          {/* Workflow Progress */}
          <div className="rounded-xl border border-border bg-card p-4">
            <h3 className="text-sm font-semibold mb-3">Workflow Progress</h3>
            <WorkflowStepper
              steps={[
                { label: "Review Patient", done: !!patient.dob || !!patient.insurance },
                { label: "Identify Gaps", done: conditions.length > 0 },
                { label: "Add HCC Codes", done: conditions.some((c: any) => c.hcc_category) },
                { label: "Submit & Log", done: callLogs.some((l: any) => l.status === "completed") },
              ]}
            />
          </div>

          {/* Patient info card */}
          {patient.notes && (
            <div className="rounded-xl border border-border bg-card p-4">
              <h3 className="text-sm font-semibold mb-2">Notes</h3>
              <p className="text-xs text-muted-foreground whitespace-pre-wrap">{patient.notes}</p>
            </div>
          )}
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

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-center px-4 py-2 rounded-lg border border-border bg-muted/30">
      <p className="text-lg font-bold font-mono text-primary">{value}</p>
      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</p>
    </div>
  );
}

function FormField({ label, value, onChange, placeholder, type }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-muted-foreground mb-1">{label}</label>
      <input
        type={type || "text"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
      />
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
            <span className={cn(
              "text-xs",
              isDone ? "text-primary font-semibold" :
              isActive ? "text-primary font-semibold" :
              "text-muted-foreground"
            )}>
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
