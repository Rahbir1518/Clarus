"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "../../components/dashboard/Sidebar";
import TopHeader from "../../components/dashboard/TopHeader";
import PatientSummary from "../../components/dashboard/PatientSummary";
import ConditionsTable from "../../components/dashboard/ConditionsTable";
import TriggerReview from "../../components/dashboard/TriggerReview";
import InsightPanel from "../../components/dashboard/InsightPanel";
import WorkflowTracker from "../../components/dashboard/WorkflowTracker";

export default function Dashboard() {
  const { isAuthenticated, isLoading } = useAuth0();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/signIn");
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-3 border-teal-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-slate-500 font-medium">
            Loading Clarus...
          </p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  return (
    <div className="min-h-screen bg-slate-100">
      <Sidebar />

      <div className="ml-64 min-h-screen flex flex-col">
        <TopHeader />

        <main className="flex-1 flex">
          <div className="flex-1 p-6 space-y-5 overflow-y-auto">
            <PatientSummary />
            <ConditionsTable />
            <TriggerReview />
            <WorkflowTracker />
          </div>

          <aside className="w-80 border-l border-slate-200 bg-slate-50/50 p-4 overflow-y-auto shrink-0">
            <InsightPanel />
          </aside>
        </main>
      </div>
    </div>
  );
}
