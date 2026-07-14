import { Link } from "react-router-dom";
import { useStats } from "../api/client";
import { StatsCard } from "../components/StatsCard";
import { StatusBadge } from "../components/StatusBadge";
import { SuccessRate } from "../components/charts/SuccessRate";
import { IssuesByStatus } from "../components/charts/IssuesByStatus";
import { CheckCircle2, ListChecks, Timer, Footprints } from "lucide-react";

export function DashboardHome() {
  const { data: stats, isLoading } = useStats();

  if (isLoading || !stats) {
    return <div className="text-slate-500">Loading dashboard…</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-100">Dashboard</h1>
        <p className="text-sm text-slate-500">Autonomous bug-fixing at a glance.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatsCard label="Total runs" value={stats.total_runs} icon={<ListChecks className="h-4 w-4" />} />
        <StatsCard
          label="Success rate"
          value={`${Math.round(stats.success_rate * 100)}%`}
          sub={`${stats.solved} solved · ${stats.failed} failed`}
          icon={<CheckCircle2 className="h-4 w-4" />}
        />
        <StatsCard label="Avg steps" value={stats.avg_steps} icon={<Footprints className="h-4 w-4" />} />
        <StatsCard
          label="Avg duration"
          value={`${(stats.avg_duration_ms / 1000).toFixed(1)}s`}
          icon={<Timer className="h-4 w-4" />}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SuccessRate runs={stats.recent} />
        <IssuesByStatus stats={stats} />
      </div>

      <div className="rounded-xl border border-line bg-panel">
        <div className="border-b border-line px-5 py-3 text-sm font-medium text-slate-300">
          Recent runs
        </div>
        <div className="divide-y divide-line">
          {stats.recent.map((r) => (
            <Link
              key={r.id}
              to={`/runs/${r.id}`}
              className="flex items-center justify-between px-5 py-3 hover:bg-panel2"
            >
              <div className="min-w-0">
                <div className="truncate text-sm text-slate-200">
                  #{r.issue_number} · {r.issue_title}
                </div>
                <div className="text-xs text-slate-500">
                  {r.total_steps} steps {r.pr_number ? `· PR #${r.pr_number}` : ""}
                </div>
              </div>
              <StatusBadge status={r.status} />
            </Link>
          ))}
          {stats.recent.length === 0 && (
            <div className="px-5 py-8 text-center text-sm text-slate-500">No runs yet.</div>
          )}
        </div>
      </div>
    </div>
  );
}
