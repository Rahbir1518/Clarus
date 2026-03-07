export type TriggerStatus = "active" | "paused" | "disabled";

export type EventType = "blood_report" | "lab_report";

export interface Trigger {
  id: string;
  name: string;
  eventType: EventType;
  status: TriggerStatus;
  conditionFilter?: "all" | "abnormal" | "requires_review";
  patientScope: "all" | "specific";
  patientIds?: string[];
  actionType: "auto_call";
  callScript: string;
  retryAttempts: number;
  retryIntervalMinutes: number;
  doctorId: string;
  createdAt: string;
  updatedAt: string;
}
