import { ClipboardCheck, AlertCircle, Clock } from "lucide-react";

interface Condition {
  icd10: string;
  description: string;
  hcc: string;
  riskImpact: "high" | "moderate" | "low";
  status: "documented" | "review_needed" | "pending_review";
}

const MOCK_CONDITIONS: Condition[] = [
  {
    icd10: "E11.65",
    description: "Type 2 Diabetes with Hyperglycemia",
    hcc: "HCC 19",
    riskImpact: "high",
    status: "documented",
  },
  {
    icd10: "I10",
    description: "Essential Hypertension",
    hcc: "HCC 85",
    riskImpact: "moderate",
    status: "documented",
  },
  {
    icd10: "E78.5",
    description: "Dyslipidemia, unspecified",
    hcc: "N/A",
    riskImpact: "low",
    status: "review_needed",
  },
  {
    icd10: "N18.3",
    description: "Chronic Kidney Disease, Stage 3",
    hcc: "HCC 138",
    riskImpact: "high",
    status: "pending_review",
  },
];

const riskBadge = {
  high: "bg-red-50 text-red-700 border-red-200",
  moderate: "bg-amber-50 text-amber-700 border-amber-200",
  low: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

const statusConfig = {
  documented: {
    label: "Documented",
    icon: ClipboardCheck,
    color: "text-emerald-600",
  },
  review_needed: {
    label: "Review Needed",
    icon: AlertCircle,
    color: "text-amber-600",
  },
  pending_review: {
    label: "Pending Review",
    icon: Clock,
    color: "text-slate-500",
  },
};

export default function ConditionsTable() {
  return (
    <div className="bg-white rounded-xl border border-slate-200">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">
            Active Problem / Condition List
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            {MOCK_CONDITIONS.length} active conditions on record
          </p>
        </div>
        <span className="text-xs text-slate-400 bg-slate-50 px-2.5 py-1 rounded-md">
          ICD-10 / HCC
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100">
              <th className="text-left px-5 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                ICD-10
              </th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Condition
              </th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                HCC Category
              </th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Risk Impact
              </th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Status
              </th>
              <th className="px-5 py-3" />
            </tr>
          </thead>
          <tbody>
            {MOCK_CONDITIONS.map((condition, idx) => {
              const status = statusConfig[condition.status];
              const StatusIcon = status.icon;
              return (
                <tr
                  key={idx}
                  className="border-b border-slate-50 last:border-0 hover:bg-slate-50/50 transition-colors"
                >
                  <td className="px-5 py-3">
                    <code className="text-xs font-mono bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                      {condition.icd10}
                    </code>
                  </td>
                  <td className="px-5 py-3 font-medium text-slate-700">
                    {condition.description}
                  </td>
                  <td className="px-5 py-3 text-slate-500">
                    {condition.hcc}
                  </td>
                  <td className="px-5 py-3">
                    <span
                      className={`inline-flex px-2 py-0.5 rounded-full text-xs font-semibold border ${riskBadge[condition.riskImpact]}`}
                    >
                      {condition.riskImpact.charAt(0).toUpperCase() +
                        condition.riskImpact.slice(1)}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <span
                      className={`inline-flex items-center gap-1.5 text-xs font-medium ${status.color}`}
                    >
                      <StatusIcon className="w-3.5 h-3.5" />
                      {status.label}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-right">
                    {condition.status !== "documented" && (
                      <button className="text-xs font-medium text-teal-600 hover:text-teal-700 hover:bg-teal-50 px-3 py-1.5 rounded-md transition-colors">
                        Review
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
