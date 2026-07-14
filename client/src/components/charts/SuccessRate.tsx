import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import type { RunSummary } from "../../types";

/** Cumulative success rate over the recent runs (oldest -> newest). */
export function SuccessRate({ runs }: { runs: RunSummary[] }) {
  const ordered = [...runs].reverse();
  let solved = 0;
  const data = ordered.map((r, i) => {
    if (r.status === "SOLVED") solved += 1;
    return { idx: i + 1, rate: Math.round((solved / (i + 1)) * 100) };
  });

  return (
    <div className="rounded-xl border border-line bg-panel p-5">
      <h3 className="mb-3 text-sm font-medium text-slate-300">Success rate trend</h3>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#222a3a" />
          <XAxis dataKey="idx" stroke="#64748b" fontSize={11} />
          <YAxis domain={[0, 100]} stroke="#64748b" fontSize={11} unit="%" />
          <Tooltip
            contentStyle={{ background: "#11151f", border: "1px solid #222a3a", borderRadius: 8 }}
          />
          <Line type="monotone" dataKey="rate" stroke="#3b82f6" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
