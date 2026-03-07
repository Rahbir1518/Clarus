import {
  Lightbulb,
  TrendingUp,
  Phone,
  AlertCircle,
  CheckCircle2,
  Clock,
  ArrowUpRight,
} from "lucide-react";

interface Insight {
  type: "gap" | "recommendation" | "status" | "metric";
  title: string;
  description: string;
  priority: "high" | "medium" | "info";
}

const MOCK_INSIGHTS: Insight[] = [
  {
    type: "gap",
    title: "Follow-up Required",
    description:
      "Patient requires follow-up after abnormal blood report received today.",
    priority: "high",
  },
  {
    type: "recommendation",
    title: "HbA1c Follow-up",
    description: "Schedule HbA1c re-test within 2 weeks based on current levels.",
    priority: "medium",
  },
  {
    type: "status",
    title: "2 Triggers Pending",
    description: "Review and approve pending triggers to initiate patient outreach.",
    priority: "medium",
  },
  {
    type: "metric",
    title: "3 Calls This Week",
    description:
      "Automated calls placed for your patients. 2 confirmed, 1 pending callback.",
    priority: "info",
  },
];

const insightIcons = {
  gap: AlertCircle,
  recommendation: Lightbulb,
  status: Clock,
  metric: Phone,
};

const priorityIndicator = {
  high: "border-l-red-500",
  medium: "border-l-amber-500",
  info: "border-l-blue-500",
};

interface StatCardProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  trend?: string;
}

function StatCard({ icon: Icon, label, value, trend }: StatCardProps) {
  return (
    <div className="bg-slate-50 rounded-lg p-3">
      <div className="flex items-center justify-between">
        <Icon className="w-4 h-4 text-slate-400" />
        {trend && (
          <span className="text-[10px] font-medium text-emerald-600 flex items-center gap-0.5">
            <ArrowUpRight className="w-3 h-3" />
            {trend}
          </span>
        )}
      </div>
      <p className="text-lg font-bold text-slate-800 mt-1">{value}</p>
      <p className="text-[11px] text-slate-400">{label}</p>
    </div>
  );
}

export default function InsightPanel() {
  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-7 h-7 rounded-lg bg-amber-100 flex items-center justify-center">
            <Lightbulb className="w-4 h-4 text-amber-600" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-800">
              Beacon Insights
            </h3>
            <p className="text-[11px] text-slate-400">
              Automation intelligence
            </p>
          </div>
        </div>

        <div className="space-y-2.5">
          {MOCK_INSIGHTS.map((insight, idx) => {
            const Icon = insightIcons[insight.type];
            return (
              <div
                key={idx}
                className={`border-l-[3px] ${priorityIndicator[insight.priority]} bg-slate-50/80 rounded-r-lg p-3`}
              >
                <div className="flex items-start gap-2">
                  <Icon className="w-3.5 h-3.5 text-slate-500 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-xs font-semibold text-slate-700">
                      {insight.title}
                    </p>
                    <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
                      {insight.description}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <h3 className="text-sm font-semibold text-slate-800 mb-3">
          Quick Stats
        </h3>
        <div className="grid grid-cols-2 gap-2">
          <StatCard
            icon={Phone}
            label="Calls Today"
            value="12"
            trend="+18%"
          />
          <StatCard
            icon={CheckCircle2}
            label="Confirmed"
            value="8"
            trend="+5%"
          />
          <StatCard
            icon={TrendingUp}
            label="Answer Rate"
            value="72%"
          />
          <StatCard
            icon={Clock}
            label="Avg Response"
            value="4.2m"
          />
        </div>
      </div>
    </div>
  );
}
