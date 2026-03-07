export type CallOutcome =
  | "answered_booked"
  | "answered_rescheduled"
  | "answered_opted_out"
  | "no_answer"
  | "unreachable"
  | "in_progress";

export interface AutomatedCall {
  id: string;
  triggerId: string;
  patientId: string;
  outcome: CallOutcome;
  attemptNumber: number;
  callDurationSeconds?: number;
  appointmentId?: string;
  initiatedAt: string;
  completedAt?: string;
}

export interface Appointment {
  id: string;
  patientId: string;
  doctorId: string;
  callId?: string;
  scheduledAt: string;
  status: "confirmed" | "cancelled" | "completed" | "no_show";
  createdAt: string;
}
