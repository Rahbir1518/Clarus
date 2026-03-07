import {
  Zap,
  FlaskConical,
  AlertTriangle,
  CheckCircle2,
  ArrowRight,
} from "lucide-react";

interface TriggerEvent {
  id: string;
  event: string;
  classification: string;
  impact: "high" | "medium" | "low";
  status: "ready" | "pending" | "processed";
  timestamp: string;
}

const MOCK_TRIGGERS: TriggerEvent[] = [
  {
    id: "TRG-001",
    event: "Blood Test Result Received",
    classification: "Type 2 Diabetes with Hyperglycemia detected",
    impact: "high",
    status: "ready",
    timestamp: "Today, 9:42 AM",
  },
  {
    id: "TRG-002",
    event: "Abnormal Lab Values",
    classification: "Creatinine elevated — eGFR declining",
    impact: "medium",
    status: "pending",
    timestamp: "Today, 8:15 AM",
  },
  {
    id: "TRG-003",
    event: "Routine Panel Complete",
    classification: "Annual wellness blood panel completed",
    impact: "low",
    status: "processed",
    timestamp: "Yesterday, 4:30 PM",
  },
];

const impactConfig = {
  high: {
    label: "High Impact",
    dot: "bg-red-500",
    bg: "bg-red-50 border-red-100",
  },
  medium: {
    label: "Medium Impact",
    dot: "bg-amber-500",
    bg: "bg-amber-50 border-amber-100",
  },
  low: {
    label: "Low Impact",
    dot: "bg-emerald-500",
    bg: "bg-emerald-50 border-emerald-100",
  },
};

const statusConfig = {
  ready: {
    label: "Ready for Review",
    icon: AlertTriangle,
    color: "text-amber-600 bg-amber-50",
  },
  pending: {
    label: "Pending",
    icon: FlaskConical,
    color: "text-slate-600 bg-slate-50",
  },
  processed: {
    label: "Auto-processed",
    icon: CheckCircle2,
    color: "text-emerald-600 bg-emerald-50",
  },
};

export default function TriggerReview() {
  return (
    <div className="bg-white rounded-xl border border-slate-200">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-teal-600" />
          <div>
            <h3 className="text-sm font-semibold text-slate-800">
              Trigger Review
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Automation events requiring attention
            </p>
          </div>
        </div>
        <span className="text-xs font-semibold text-teal-700 bg-teal-50 px-2.5 py-1 rounded-full">
          {MOCK_TRIGGERS.filter((t) => t.status !== "processed").length} pending
        </span>
      </div>

      <div className="p-4 space-y-3">
        {MOCK_TRIGGERS.map((trigger) => {
          const impact = impactConfig[trigger.impact];
          const status = statusConfig[trigger.status];
          const StatusIcon = status.icon;

          return (
            <div
              key={trigger.id}
              className={`rounded-lg border p-4 transition-colors ${
                trigger.status === "ready"
                  ? "border-teal-200 bg-teal-50/30"
                  : "border-slate-100 bg-white"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h4 className="text-sm font-semibold text-slate-800">
                      {trigger.event}
                    </h4>
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border ${impact.bg}`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${impact.dot}`}
                      />
                      {impact.label}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    {trigger.classification}
                  </p>
                  <div className="flex items-center gap-3 mt-2">
                    <span className="text-[11px] text-slate-400">
                      {trigger.id}
                    </span>
                    <span className="text-[11px] text-slate-400">
                      {trigger.timestamp}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium ${status.color}`}
                  >
                    <StatusIcon className="w-3 h-3" />
                    {status.label}
                  </span>
                  {trigger.status === "ready" && (
                    <button className="inline-flex items-center gap-1 px-3 py-1.5 bg-teal-600 hover:bg-teal-700 text-white rounded-md text-xs font-medium transition-colors">
                      Review
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
