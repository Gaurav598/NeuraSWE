import { NavLink } from "react-router-dom";
import { LayoutDashboard, ListChecks, FolderGit2, BarChart3, Bot, CircleDot } from "lucide-react";

const links = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/runs", label: "Runs", icon: ListChecks },
  { to: "/issues", label: "Issues", icon: CircleDot },
  { to: "/repositories", label: "Repositories", icon: FolderGit2 },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
];

export function Sidebar() {
  return (
    <aside className="flex w-60 flex-col border-r border-line bg-panel">
      <div className="flex items-center gap-2 px-5 py-5">
        <Bot className="h-7 w-7 text-blue-400" />
        <div>
          <div className="text-lg font-semibold text-slate-100">NeuraSWE</div>
          <div className="text-[11px] text-slate-500">Autonomous SWE Agent</div>
        </div>
      </div>
      <nav className="mt-2 flex flex-col gap-1 px-3">
        {links.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                isActive
                  ? "bg-blue-500/15 text-blue-300"
                  : "text-slate-400 hover:bg-panel2 hover:text-slate-200"
              }`
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto px-5 py-4 text-[11px] text-slate-600">
        Local LLM · ReAct loop · RAG
      </div>
    </aside>
  );
}
