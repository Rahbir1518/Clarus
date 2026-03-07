"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { listCallLogs } from "@/services/api";

import { cn } from "@/lib/utils";
import { Calendar, CheckCircle2, Clock, AlertCircle } from "lucide-react";

export default function AppointmentsPage() {
  const { user } = useAuth0();
  const doctorId = user?.sub;

  const [callLogs, setCallLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchLogs = useCallback(async () => {
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
    fetchLogs();
  }, [fetchLogs]);

  const appointmentLogs = callLogs.filter((cl) => {
    const execLog: any[] = Array.isArray(cl.execution_log) ? cl.execution_log : [];
    return execLog.some(
      (step) =>
        step.node_type === "schedule_appointment" ||
        step.confirmed_date ||
        step.call_outcome === "appointment_booked"
    );
  });

  const appointments = appointmentLogs.map((cl) => {
    const execLog: any[] = Array.isArray(cl.execution_log) ? cl.execution_log : [];
    const calStep = execLog.find(
      (s) => s.node_type === "schedule_appointment" || s.confirmed_date
    );
    return {
      id: cl.id,
      patientId: cl.patient_id,
      workflowId: cl.workflow_id,
      date: calStep?.confirmed_date || "—",
      time: calStep?.confirmed_time || "—",
      doctorName: calStep?.doctor_name || "—",
      status: calStep?.status === "ok" ? "confirmed" : calStep?.status === "error" ? "failed" : "pending",
      calendarEventId: calStep?.calendar_event_id,
      createdAt: cl.created_at,
    };
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Appointments</h1>
        <p className="text-sm text-muted-foreground">
          Appointments booked via automated workflows.
          {!loading && ` ${appointments.length} appointment${appointments.length !== 1 ? "s" : ""} found.`}
        </p>
      </div>

      {loading ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center text-sm text-muted-foreground">
          Loading appointments…
        </div>
      ) : appointments.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center">
          <Calendar className="size-10 text-muted-foreground/40 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">
            No appointments yet. Appointments will appear here when workflows book them via call interactions.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {appointments.map((apt) => {
            const StatusIcon =
              apt.status === "confirmed" ? CheckCircle2 :
              apt.status === "failed" ? AlertCircle :
              Clock;
            const statusStyle =
              apt.status === "confirmed" ? "bg-success/10 text-success" :
              apt.status === "failed" ? "bg-destructive/10 text-destructive" :
              "bg-muted text-muted-foreground";

            return (
              <div key={apt.id} className="rounded-xl border border-border bg-card p-5">
                <div className="flex items-start gap-4">
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Calendar className="size-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize", statusStyle)}>
                        <StatusIcon className="size-3" />
                        {apt.status}
                      </span>
                      {apt.doctorName !== "—" && (
                        <span className="text-xs text-muted-foreground">{apt.doctorName}</span>
                      )}
                    </div>
                    <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                      <span>Date: <strong className="text-foreground">{apt.date}</strong></span>
                      <span>Time: <strong className="text-foreground">{apt.time}</strong></span>
                      <span>Patient: <code className="bg-muted px-1.5 py-0.5 rounded font-mono text-[10px]">{apt.patientId?.slice(0, 8)}…</code></span>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-[10px] text-muted-foreground">
                      <span>Created: {new Date(apt.createdAt).toLocaleString()}</span>
                      {apt.calendarEventId && <span>Calendar ID: {apt.calendarEventId}</span>}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
