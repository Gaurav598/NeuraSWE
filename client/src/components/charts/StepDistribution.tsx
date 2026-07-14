import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import type { RunSummary } from "../../types";

/** Distribution of step counts across completed runs. */
export function StepDistribution({ runs }: { runs: RunSummary[] }) {
  const buckets: Record<string, number> = { "1-5": 0, "6-10": 0, "11-15": 0, "16-20": 0, "21-25": 0 };
  runs.forEach((r) => {
    const s = r.total_steps;
    if (s <= 5) buckets["1-5"] += 1;
    else if (s <= 10) buckets["6-10"] += 1;
    else if (s <= 15) buckets["11-15"] += 1;
    else if (s <= 20) buckets["16-20"] += 1;
    else buckets["21-25"] += 1;
  });
  const data = Object.entries(buckets).map(([range, count]) => ({ range, count }));

  return (
    <div className="rounded-xl border border-line bg-panel p-5">
      <h3 className="mb-3 text-sm font-medium text-slate-300">Steps to solve</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#222a3a" />
          <XAxis dataKey="range" stroke="#64748b" fontSize={11} />
          <YAxis stroke="#64748b" fontSize={11} allowDecimals={false} />
          <Tooltip
            contentStyle={{ background: "#11151f", border: "1px solid #222a3a", borderRadius: 8 }}
            cursor={{ fill: "#ffffff08" }}
          />
          <Bar dataKey="count" fill="#22c55e" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
