import Link from "next/link";
import {
  UserCheck,
  Zap,
  ClipboardEdit,
  Send,
  ArrowRight,
} from "lucide-react";

interface WorkflowStep {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  status: "completed" | "active" | "upcoming";
}

const STEPS: WorkflowStep[] = [
  { label: "Review Patient", icon: UserCheck, status: "completed" },
  { label: "Identify Triggers", icon: Zap, status: "active" },
  { label: "Confirm Data", icon: ClipboardEdit, status: "upcoming" },
  { label: "Submit / Activate", icon: Send, status: "upcoming" },
];

const stepStyles = {
  completed: {
    circle: "bg-teal-600 text-white",
    label: "text-teal-700 font-semibold",
    connector: "bg-teal-600",
  },
  active: {
    circle: "bg-white border-2 border-teal-600 text-teal-600 ring-4 ring-teal-100",
    label: "text-teal-700 font-semibold",
    connector: "bg-slate-200",
  },
  upcoming: {
    circle: "bg-slate-100 text-slate-400 border border-slate-200",
    label: "text-slate-400",
    connector: "bg-slate-200",
  },
};

export default function WorkflowTracker() {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">
            Workflow Progress
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Current automation lifecycle status
          </p>
        </div>
        <Link
          href="/workflow"
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          Open Workflow
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>

      <div className="flex items-center">
        {STEPS.map((step, idx) => {
          const styles = stepStyles[step.status];
          const StepIcon = step.icon;
          const isLast = idx === STEPS.length - 1;

          return (
            <div key={idx} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center">
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center transition-all ${styles.circle}`}
                >
                  <StepIcon className="w-[18px] h-[18px]" />
                </div>
                <p
                  className={`text-xs mt-2 text-center whitespace-nowrap ${styles.label}`}
                >
                  {step.label}
                </p>
              </div>
              {!isLast && (
                <div className="flex-1 mx-3 -mt-5">
                  <div
                    className={`h-0.5 w-full rounded-full ${styles.connector}`}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
