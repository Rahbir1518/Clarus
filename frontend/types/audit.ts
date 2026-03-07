export interface AuditLogEntry {
  id: string;
  timestamp: string;
  patientId: string;
  triggerName: string;
  triggerId: string;
  actionTaken: string;
  callOutcome?: string;
  doctorId: string;
  details?: string;
}
