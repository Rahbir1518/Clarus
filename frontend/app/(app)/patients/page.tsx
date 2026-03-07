"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { listPatients, createPatient, deletePatient } from "@/services/api";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Users,
  UserPlus,
  Trash2,
  Search,
  X,
  Phone,
  ArrowRight,
  Shield,
  AlertTriangle,
} from "lucide-react";

export default function PatientsPage() {
  const [patients, setPatients] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [showAddPatient, setShowAddPatient] = useState(false);
  const [patientName, setPatientName] = useState("");
  const [patientPhone, setPatientPhone] = useState("");
  const [savingPatient, setSavingPatient] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const { user } = useAuth0();
  const doctorId = user?.sub;

  const fetchPatients = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listPatients(doctorId);
      setPatients(Array.isArray(data) ? data : []);
    } catch {
      setPatients([]);
    } finally {
      setLoading(false);
    }
  }, [doctorId]);

  useEffect(() => {
    fetchPatients();
  }, [fetchPatients]);

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

  const handleDelete = useCallback(async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm("Delete this patient? This cannot be undone.")) return;
    setDeletingId(id);
    try {
      await deletePatient(id);
      setPatients((prev) => prev.filter((p) => p.id !== id));
    } catch {
      /* ignore */
    } finally {
      setDeletingId(null);
    }
  }, []);

  const filtered = patients.filter((p) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      p.name?.toLowerCase().includes(q) ||
      p.phone?.includes(q) ||
      p.id?.includes(q) ||
      p.mrn?.toLowerCase().includes(q) ||
      p.insurance?.toLowerCase().includes(q)
    );
  });

  const riskBadge = (level: string) => {
    if (level === "high") return "bg-destructive/10 text-destructive";
    if (level === "moderate") return "bg-warning/10 text-warning";
    return null;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Patients</h1>
          <p className="text-sm text-muted-foreground">
            Manage your patient list. {!loading && `${patients.length} patient${patients.length !== 1 ? "s" : ""} registered.`}
          </p>
        </div>
        <Button onClick={() => setShowAddPatient(true)}>
          <UserPlus className="size-4" />
          Add Patient
        </Button>
      </div>

      <div className="relative max-w-xs">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name, phone, MRN…"
          className="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-background text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
        />
        {search && (
          <button onClick={() => setSearch("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
            <X className="size-3.5" />
          </button>
        )}
      </div>

      {loading ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center text-sm text-muted-foreground">
          Loading patients…
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center">
          <Users className="size-10 text-muted-foreground/40 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">
            {patients.length === 0
              ? "No patients yet. Add your first patient."
              : "No patients match your search."}
          </p>
          {patients.length === 0 && (
            <Button size="sm" className="mt-3" onClick={() => setShowAddPatient(true)}>
              Add Patient
            </Button>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Patient</th>
                <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Phone</th>
                <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Insurance</th>
                <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">MRN</th>
                <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Risk</th>
                <th className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => {
                const badge = riskBadge(p.risk_level);
                return (
                  <tr key={p.id} className="border-b border-border/50 last:border-0 hover:bg-muted/30 transition-colors group">
                    <td className="px-5 py-3">
                      <Link href={`/patients/${p.id}`} className="flex items-center gap-3">
                        <div className="flex size-8 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-semibold">
                          {p.name
                            ?.split(" ")
                            .map((n: string) => n[0])
                            .join("")
                            .slice(0, 2)
                            .toUpperCase() || "?"}
                        </div>
                        <div>
                          <span className="font-medium group-hover:text-primary transition-colors">{p.name}</span>
                          {p.dob && <p className="text-[10px] text-muted-foreground">DOB: {p.dob}</p>}
                        </div>
                      </Link>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-1.5 text-muted-foreground">
                        <Phone className="size-3" />
                        {p.phone}
                      </div>
                    </td>
                    <td className="px-5 py-3 text-muted-foreground text-xs">
                      {p.insurance ? (
                        <div className="flex items-center gap-1">
                          <Shield className="size-3" />
                          {p.insurance}
                        </div>
                      ) : "—"}
                    </td>
                    <td className="px-5 py-3">
                      {p.mrn ? (
                        <code className="rounded bg-muted px-2 py-0.5 font-mono text-xs">{p.mrn}</code>
                      ) : (
                        <span className="text-muted-foreground text-xs">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      {badge ? (
                        <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold", badge)}>
                          <AlertTriangle className="size-3" />
                          {p.risk_level?.charAt(0).toUpperCase() + p.risk_level?.slice(1)}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">Low</span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex items-center gap-1 justify-end">
                        <Link href={`/patients/${p.id}`}>
                          <Button size="sm" variant="ghost">
                            View
                            <ArrowRight className="size-3" />
                          </Button>
                        </Link>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={deletingId === p.id}
                          onClick={(e) => handleDelete(e, p.id)}
                          className="text-destructive hover:text-destructive hover:bg-destructive/10"
                        >
                          <Trash2 className="size-3.5" />
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
    </div>
  );
}
