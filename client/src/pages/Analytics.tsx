import { useStats } from "../api/client";
import { SuccessRate } from "../components/charts/SuccessRate";
import { StepDistribution } from "../components/charts/StepDistribution";
import { IssuesByStatus } from "../components/charts/IssuesByStatus";
import { StatsCard } from "../components/StatsCard";

export function Analytics() {
  const { data: stats, isLoading } = useStats();
  if (isLoading || !stats) return <div className="text-slate-500">Loading analytics…</div>;

  const minutesSaved = Math.round((stats.solved * 45) / 60); // ~45 min/issue assumption

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-slate-100">Analytics</h1>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatsCard label="Issues solved" value={stats.solved} />
        <StatsCard label="Success rate" value={`${Math.round(stats.success_rate * 100)}%`} />
        <StatsCard label="Est. engineer-hours saved" value={`${minutesSaved}h`} sub="~45 min/issue" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SuccessRate runs={stats.recent} />
        <StepDistribution runs={stats.recent} />
      </div>
      <IssuesByStatus stats={stats} />
    </div>
  );
}
