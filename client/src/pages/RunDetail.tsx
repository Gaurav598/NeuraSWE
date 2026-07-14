import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, GitPullRequest, Radio } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteRun, stopRun, useRun } from "../api/client";
import { useLiveRun } from "../socket/useSocket";
import { StatusBadge } from "../components/StatusBadge";
import { ReasoningTimeline } from "../components/timeline/ReasoningTimeline";
import { FileTree } from "../components/code/FileTree";
import { DiffViewer } from "../components/code/DiffViewer";
import { AgentActivity } from "../components/AgentActivity";

export function RunDetail() {
  const { id } = useParams();
  const [actionError, setActionError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { data: run, isLoading, refetch } = useRun(id);
  const { events, connected, completed } = useLiveRun(id);
  const stop = useMutation({
    mutationFn: stopRun,
    onSuccess: () => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      queryClient.invalidateQueries({ queryKey: ["run", id] });
      refetch();
    },
    onError: (error: any) => setActionError(error?.response?.data?.detail || "Unable to stop run."),
  });
  const deleteCurrent = useMutation({
    mutationFn: deleteRun,
    onSuccess: () => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      window.location.href = "/runs";
    },
    onError: (error: any) => setActionError(error?.response?.data?.detail || "Unable to delete run."),
  });

  // Refetch persisted run whenever a step completes or the run finishes.
  const observeCount = events.filter((e) => e.type === "observe").length;
  useEffect(() => {
    if (observeCount > 0 || completed) refetch();
  }, [observeCount, completed, refetch]);

  if (isLoading || !run) {
    return <div className="text-slate-500">Loading run…</div>;
  }

  const touchedFiles = Array.from(
    new Set(
      run.steps
        .filter((s) => s.tool_name === "edit_file" || s.tool_name === "create_file")
        .map((s) => (s.tool_args as any)?.path)
        .filter(Boolean)
    )
  );

  const lastDiffStep = [...run.steps].reverse().find((s) => s.tool_name === "git_diff");
  const diff = lastDiffStep?.observation || "";
  const isLive = run.status === "RUNNING" || run.status === "QUEUED";
  const visibleStepCount = Math.max(run.total_steps, run.steps.length);

  return (
    <div className="space-y-5">
      <Link to="/runs" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200">
        <ArrowLeft className="h-4 w-4" /> Back to runs
      </Link>
      {actionError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {actionError}
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(300px,380px)_minmax(0,1fr)] 2xl:grid-cols-[minmax(360px,460px)_minmax(0,1fr)_minmax(420px,560px)]">
        {/* Left: issue metadata */}
        <div className="min-w-0 space-y-4">
          <div className="rounded-xl border border-line bg-panel p-5">
            <div className="mb-2 flex items-center justify-between">
              <StatusBadge status={run.status} />
              {isLive && (
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-1 text-xs text-blue-300">
                    <Radio className={`h-3 w-3 ${connected ? "text-green-400" : "text-slate-500"}`} />
                    live
                  </span>
                  <button
                    disabled={!id || stop.isPending}
                    onClick={() => {
                      if (!id) return;
                      setActionError(null);
                      stop.mutate(id);
                    }}
                    className="rounded-md border border-red-500/40 px-2.5 py-1 text-xs text-red-300 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {stop.isPending ? "Stopping…" : "Stop"}
                  </button>
                </div>
              )}
              {!isLive && (
                <button
                  disabled={!id || deleteCurrent.isPending}
                  onClick={() => {
                    if (!id) return;
                    setActionError(null);
                    deleteCurrent.mutate(id);
                  }}
                  className="rounded-md border border-line px-2.5 py-1 text-xs text-slate-400 hover:bg-panel2 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {deleteCurrent.isPending ? "Deleting…" : "Delete"}
                </button>
              )}
            </div>
            <h2 className="text-base font-medium text-slate-100">
              {run.source === "jira" && run.external_issue_key ? run.external_issue_key : `Issue #${run.issue_number}`}
            </h2>
            <p className="mt-1 text-sm text-slate-300">{run.issue_title}</p>
            {run.issue_body && (
              <p className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line/70 bg-panel2/40 p-3 text-xs text-slate-500">
                {run.issue_body}
              </p>
            )}
            <div className="mt-4 space-y-1 text-xs text-slate-500">
              <div>Source: {run.source === "jira" ? "Jira" : "GitHub"}</div>
              <div>Model: {run.model || "—"}</div>
              <div>Steps: {visibleStepCount}</div>
              <div>Duration: {run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : "—"}</div>
            </div>
            {run.external_issue_url && (
              <a
                href={run.external_issue_url}
                target="_blank"
                className="mt-4 flex items-center justify-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-slate-300 hover:bg-panel2"
              >
                Open source issue
              </a>
            )}
            {run.error_message && (
              <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">
                <div className="mb-1 font-medium text-red-100">Failure reason</div>
                <div className="max-h-48 overflow-auto whitespace-pre-wrap break-words">{run.error_message}</div>
              </div>
            )}
            {run.pr_url && (
              <a
                href={run.pr_url}
                target="_blank"
                className="mt-4 flex items-center justify-center gap-2 rounded-lg bg-green-500/15 px-3 py-2 text-sm text-green-300"
              >
                <GitPullRequest className="h-4 w-4" /> View PR #{run.pr_number}
              </a>
            )}
          </div>

          <div className="rounded-xl border border-line bg-panel p-5">
            <h3 className="mb-2 text-sm font-medium text-slate-300">Tests</h3>
            <TestRow label="Baseline" data={run.baseline_tests} />
            <TestRow label="After fix" data={run.final_tests} />
          </div>
        </div>

        {/* Center: reasoning timeline */}
        <div className="min-w-0 space-y-5">
          <AgentActivity steps={run.steps} live={events} />
          <div className="rounded-xl border border-line bg-panel p-5">
            <h3 className="mb-4 text-sm font-medium text-slate-300">Reasoning trace</h3>
            <ReasoningTimeline steps={run.steps} live={events} />
          </div>
        </div>

        {/* Right: touched files + diff */}
        <div className="min-w-0 space-y-4 lg:col-span-2 2xl:col-span-1">
          <div className="rounded-xl border border-line bg-panel p-5">
            <h3 className="mb-3 text-sm font-medium text-slate-300">Files touched</h3>
            <FileTree files={touchedFiles} />
          </div>
          <div className="rounded-xl border border-line bg-panel p-5">
            <h3 className="mb-3 text-sm font-medium text-slate-300">Diff</h3>
            <DiffViewer diff={diff} />
          </div>
        </div>
      </div>
    </div>
  );
}

function TestRow({ label, data }: { label: string; data: Record<string, any> | null }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1 text-xs">
      <span className="shrink-0 text-slate-500">{label}</span>
      <span className="break-words text-right text-slate-300">
        {data ? `${data.passed ?? "?"} pass / ${data.failed ?? 0} fail` : "—"}
      </span>
    </div>
  );
}
