import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteFailedRuns, deleteRun, stopActiveRuns, stopRun, useRuns } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import type { RunStatus } from "../types";

const STATUSES: (RunStatus | "")[] = ["", "QUEUED", "RUNNING", "SOLVED", "FAILED", "TIMEOUT"];

export function RunsList() {
  const [status, setStatus] = useState<string>("");
  const [page, setPage] = useState(1);
  const [actionError, setActionError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { data, isLoading } = useRuns({ status: status || undefined, page });
  const refreshRuns = () => {
    queryClient.invalidateQueries({ queryKey: ["runs"] });
    queryClient.invalidateQueries({ queryKey: ["stats"] });
  };
  const stopOne = useMutation({
    mutationFn: stopRun,
    onSuccess: () => {
      setActionError(null);
      refreshRuns();
    },
    onError: (error: any) => setActionError(error?.response?.data?.detail || "Unable to stop run."),
  });
  const stopAll = useMutation({
    mutationFn: stopActiveRuns,
    onSuccess: () => {
      setActionError(null);
      refreshRuns();
    },
    onError: (error: any) => setActionError(error?.response?.data?.detail || "Unable to stop active runs."),
  });
  const deleteOne = useMutation({
    mutationFn: deleteRun,
    onSuccess: () => {
      setActionError(null);
      refreshRuns();
    },
    onError: (error: any) => setActionError(error?.response?.data?.detail || "Unable to delete run."),
  });
  const deleteFailed = useMutation({
    mutationFn: deleteFailedRuns,
    onSuccess: () => {
      setActionError(null);
      refreshRuns();
    },
    onError: (error: any) => setActionError(error?.response?.data?.detail || "Unable to delete failed runs."),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Runs</h1>
          <p className="mt-1 text-sm text-slate-500">
            Latest agent attempts, provider status, and PR results.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            disabled={stopAll.isPending}
            onClick={() => {
              setActionError(null);
              stopAll.mutate();
            }}
            className="rounded-lg border border-red-500/40 px-3 py-1.5 text-sm text-red-300 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {stopAll.isPending ? "Stopping…" : "Stop all active"}
          </button>
          <button
            disabled={deleteFailed.isPending}
            onClick={() => {
              setActionError(null);
              deleteFailed.mutate();
            }}
            className="rounded-lg border border-line px-3 py-1.5 text-sm text-slate-300 hover:bg-panel2 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {deleteFailed.isPending ? "Deleting…" : "Delete failed"}
          </button>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-line bg-panel px-3 py-1.5 text-sm text-slate-300"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s || "All statuses"}
              </option>
            ))}
          </select>
        </div>
      </div>
      {actionError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {actionError}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-line bg-panel">
        <div className="overflow-x-auto">
        <table className="min-w-[880px] w-full text-sm">
          <thead className="border-b border-line text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-5 py-3">Issue</th>
              <th className="px-5 py-3">Status</th>
              <th className="px-5 py-3">Steps</th>
              <th className="px-5 py-3">Duration</th>
              <th className="px-5 py-3">PR</th>
              <th className="px-5 py-3">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-slate-500">
                  Loading…
                </td>
              </tr>
            )}
            {data?.items.map((r) => (
              <tr key={r.id} className="hover:bg-panel2">
                <td className="max-w-[360px] px-5 py-3">
                  <Link
                    to={`/runs/${r.id}`}
                    className="block truncate text-slate-200 hover:text-blue-300"
                    title={`#${r.issue_number} · ${r.issue_title}`}
                  >
                    #{r.issue_number} · {r.issue_title || "Untitled issue"}
                  </Link>
                  <div className="mt-1 truncate text-xs text-slate-600">{r.model || "No model recorded"}</div>
                </td>
                <td className="px-5 py-3">
                  <StatusBadge status={r.status} />
                </td>
                <td className="px-5 py-3 text-slate-400">{r.total_steps}</td>
                <td className="px-5 py-3 text-slate-400">
                  {r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : "—"}
                </td>
                <td className="px-5 py-3 text-slate-400">
                  {r.pr_url ? (
                    <a href={r.pr_url} target="_blank" className="text-blue-300">
                      #{r.pr_number}
                    </a>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-5 py-3">
                  {r.status === "QUEUED" || r.status === "RUNNING" ? (
                    <button
                      disabled={stopOne.isPending}
                      onClick={() => {
                        setActionError(null);
                        stopOne.mutate(r.id);
                      }}
                      className="rounded-md border border-red-500/40 px-2.5 py-1 text-xs text-red-300 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Stop
                    </button>
                  ) : (
                    <button
                      disabled={deleteOne.isPending}
                      onClick={() => {
                        setActionError(null);
                        deleteOne.mutate(r.id);
                      }}
                      className="rounded-md border border-line px-2.5 py-1 text-xs text-slate-400 hover:bg-panel2 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-slate-500">
                  No runs found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>

      {data && data.total > data.page_size && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="rounded-lg border border-line px-3 py-1.5 text-slate-300 disabled:opacity-40"
          >
            Prev
          </button>
          <span className="text-slate-500">
            Page {data.page} of {Math.ceil(data.total / data.page_size)}
          </span>
          <button
            disabled={page >= Math.ceil(data.total / data.page_size)}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-lg border border-line px-3 py-1.5 text-slate-300 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
