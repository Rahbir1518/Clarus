import {
  User,
  Calendar,
  Shield,
  Hash,
  Stethoscope,
  AlertTriangle,
} from "lucide-react";

interface PatientData {
  name: string;
  initials: string;
  dob: string;
  age: number;
  mrn: string;
  insurance: string;
  lastVisit: string;
  physician: string;
  riskLevel: "low" | "moderate" | "high";
}

const MOCK_PATIENT: PatientData = {
  name: "James Thompson",
  initials: "JT",
  dob: "May 15, 1978",
  age: 47,
  mrn: "MRN-2024-0847",
  insurance: "Blue Cross Blue Shield — PPO",
  lastVisit: "Feb 28, 2026",
  physician: "Dr. Priya Nair",
  riskLevel: "high",
};

const riskConfig = {
  low: { label: "Low Risk", color: "bg-emerald-100 text-emerald-700" },
  moderate: { label: "Moderate Risk", color: "bg-amber-100 text-amber-700" },
  high: { label: "High Risk", color: "bg-red-100 text-red-700" },
};

export default function PatientSummary() {
  const p = MOCK_PATIENT;
  const risk = riskConfig[p.riskLevel];

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-start gap-4">
        <div className="w-14 h-14 rounded-full bg-linear-to-br from-teal-500 to-teal-700 flex items-center justify-center text-white text-lg font-bold shrink-0">
          {p.initials}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="text-xl font-bold text-slate-800">{p.name}</h2>
            <span
              className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold ${risk.color}`}
            >
              <AlertTriangle className="w-3 h-3" />
              {risk.label}
            </span>
          </div>

          <div className="mt-3 grid grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-2.5">
            <InfoItem icon={Calendar} label="Date of Birth" value={`${p.dob} (Age ${p.age})`} />
            <InfoItem icon={Hash} label="MRN" value={p.mrn} />
            <InfoItem icon={Shield} label="Insurance" value={p.insurance} />
            <InfoItem icon={User} label="Last Visit" value={p.lastVisit} />
            <InfoItem icon={Stethoscope} label="Primary Physician" value={p.physician} />
          </div>
        </div>
      </div>
    </div>
  );
}

function InfoItem({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-2">
      <Icon className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
      <div>
        <p className="text-[11px] text-slate-400 font-medium uppercase tracking-wider">
          {label}
        </p>
        <p className="text-sm text-slate-700 font-medium">{value}</p>
      </div>
    </div>
  );
}
