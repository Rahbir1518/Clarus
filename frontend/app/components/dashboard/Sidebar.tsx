"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  Calendar,
  FileText,
  Pill,
  BarChart3,
  Settings,
  Activity,
  Zap,
} from "lucide-react";

const navItems = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Patients", href: "#", icon: Users },
  { name: "Schedule", href: "#", icon: Calendar },
  { name: "Orders / Reports", href: "#", icon: FileText },
  { name: "Medications", href: "#", icon: Pill },
  { name: "Analytics", href: "#", icon: BarChart3 },
  { name: "Settings", href: "#", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-64 bg-slate-900 text-white flex flex-col z-50">
      <div className="px-6 py-5 border-b border-slate-700/50">
        <Link href="/dashboard" className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-teal-500 flex items-center justify-center">
            <Activity className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight">Clarus</h1>
            <p className="text-[11px] text-slate-400 -mt-0.5">
              Clinical Automation
            </p>
          </div>
        </Link>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-teal-500/15 text-teal-400"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white"
              }`}
            >
              <item.icon className="w-[18px] h-[18px] shrink-0" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      <div className="px-3 pb-4">
        <Link
          href="/workflow"
          className="flex items-center justify-center gap-2 w-full px-4 py-3 bg-teal-600 hover:bg-teal-500 text-white rounded-lg text-sm font-semibold transition-colors"
        >
          <Zap className="w-4 h-4" />
          Workflow Studio
        </Link>
      </div>

      <div className="px-4 py-3 border-t border-slate-700/50">
        <p className="text-[10px] text-slate-500 text-center">
          Clarus v1.0 — HIPAA Compliant
        </p>
      </div>
    </aside>
  );
}
