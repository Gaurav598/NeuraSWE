import type { RunStatus, IndexStatus } from "../types";

const RUN_COLORS: Record<RunStatus, string> = {
  QUEUED: "bg-slate-500/20 text-slate-300 border-slate-500/40",
  RUNNING: "bg-blue-500/20 text-blue-300 border-blue-500/40 animate-pulse",
  SOLVED: "bg-green-500/20 text-green-300 border-green-500/40",
  FAILED: "bg-red-500/20 text-red-300 border-red-500/40",
  TIMEOUT: "bg-amber-500/20 text-amber-300 border-amber-500/40",
};

const INDEX_COLORS: Record<IndexStatus, string> = {
  PENDING: "bg-slate-500/20 text-slate-300 border-slate-500/40",
  INDEXING: "bg-blue-500/20 text-blue-300 border-blue-500/40 animate-pulse",
  READY: "bg-green-500/20 text-green-300 border-green-500/40",
  FAILED: "bg-red-500/20 text-red-300 border-red-500/40",
};

export function StatusBadge({ status }: { status: RunStatus | IndexStatus }) {
  const color =
    (RUN_COLORS as any)[status] || (INDEX_COLORS as any)[status] || RUN_COLORS.QUEUED;
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}
