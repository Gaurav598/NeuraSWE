import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from "recharts";
import type { Stats } from "../../types";

const COLORS = ["#22c55e", "#ef4444", "#3b82f6"];

export function IssuesByStatus({ stats }: { stats: Stats }) {
  const data = [
    { name: "Solved", value: stats.solved },
    { name: "Failed", value: stats.failed },
    { name: "In progress", value: stats.in_progress },
  ];
  return (
    <div className="rounded-xl border border-line bg-panel p-5">
      <h3 className="mb-3 text-sm font-medium text-slate-300">Issues by status</h3>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={3}>
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ background: "#11151f", border: "1px solid #222a3a", borderRadius: 8 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
