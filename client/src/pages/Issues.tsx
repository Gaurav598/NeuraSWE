import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ExternalLink, Loader2, Play, RefreshCw, Search } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { triggerManualRun, useRepositories, useRepositoryIssues } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import type { GitHubIssue, Repository } from "../types";

const PAGE_SIZE = 50;

export function Issues() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: repos, isLoading: reposLoading } = useRepositories();
  const readyRepos = useMemo(() => repos?.filter((repo) => repo.index_status === "READY") ?? [], [repos]);
  const [repoId, setRepoId] = useState("");
  const [state, setState] = useState("open");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [solvingIssue, setSolvingIssue] = useState<number | null>(null);

  const selectedRepo = repos?.find((repo) => repo.id === (repoId || readyRepos[0]?.id));
  const selectedRepoId = selectedRepo?.id;
  const issues = useRepositoryIssues(selectedRepoId, { state, page, page_size: PAGE_SIZE });

  const filteredIssues = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return issues.data?.items ?? [];
    return (issues.data?.items ?? []).filter((issue) => {
      return (
        issue.title.toLowerCase().includes(needle) ||
        issue.body.toLowerCase().includes(needle) ||
        String(issue.number).includes(needle) ||
        issue.labels.some((label) => label.name.toLowerCase().includes(needle))
      );
    });
  }, [issues.data?.items, search]);

  async function solve(issue: GitHubIssue) {
    if (!selectedRepoId) return;
    setSolvingIssue(issue.number);
    try {
      const run = await triggerManualRun(selectedRepoId, issue.number);
      qc.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/runs/${run.id}`);
    } finally {
      setSolvingIssue(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Issues</h1>
          <p className="mt-1 text-sm text-slate-500">
            Fetch GitHub issues, choose one, and start an NeuraSWE run directly.
          </p>
        </div>
        <button
          onClick={() => issues.refetch()}
          disabled={!selectedRepoId || issues.isFetching}
          className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-slate-300 hover:bg-panel2 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${issues.isFetching ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      <div className="rounded-xl border border-line bg-panel p-5">
        <div className="grid gap-3 lg:grid-cols-[minmax(260px,1fr)_160px_minmax(240px,360px)]">
          <label className="space-y-1">
            <span className="text-xs text-slate-500">Repository</span>
            <select
              value={selectedRepoId ?? ""}
              onChange={(event) => {
                setRepoId(event.target.value);
                setPage(1);
              }}
              className="w-full rounded-lg border border-line bg-ink px-3 py-2 text-sm text-slate-200"
            >
              {readyRepos.map((repo) => (
                <option key={repo.id} value={repo.id}>
                  {repo.owner}/{repo.name}
                </option>
              ))}
              {repos?.filter((repo) => repo.index_status !== "READY").map((repo) => (
                <option key={repo.id} value={repo.id}>
                  {repo.owner}/{repo.name} ({repo.index_status})
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-1">
            <span className="text-xs text-slate-500">State</span>
            <select
              value={state}
              onChange={(event) => {
                setState(event.target.value);
                setPage(1);
              }}
              className="w-full rounded-lg border border-line bg-ink px-3 py-2 text-sm text-slate-200"
            >
              <option value="open">Open</option>
              <option value="closed">Closed</option>
              <option value="all">All</option>
            </select>
          </label>

          <label className="space-y-1">
            <span className="text-xs text-slate-500">Search current page</span>
            <div className="flex items-center gap-2 rounded-lg border border-line bg-ink px-3 py-2">
              <Search className="h-4 w-4 text-slate-500" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="title, label, number"
                className="min-w-0 flex-1 bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-600"
              />
            </div>
          </label>
        </div>

        {selectedRepo && (
          <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-slate-500">
            <span>
              Selected: {selectedRepo.owner}/{selectedRepo.name}
            </span>
            <StatusBadge status={selectedRepo.index_status} />
            {selectedRepo.index_status !== "READY" && <span>Index must be READY before solving issues.</span>}
          </div>
        )}
      </div>

      <IssuesBody
        reposLoading={reposLoading}
        selectedRepo={selectedRepo}
        issuesLoading={issues.isLoading}
        issuesError={issues.error}
        issues={filteredIssues}
        solvingIssue={solvingIssue}
        onSolve={solve}
      />

      {issues.data && (
        <div className="flex items-center justify-between rounded-xl border border-line bg-panel p-4 text-sm">
          <button
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            disabled={page <= 1}
            className="rounded-lg border border-line px-3 py-1.5 text-slate-300 hover:bg-panel2 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-slate-500">Page {page}</span>
          <button
            onClick={() => setPage((value) => value + 1)}
            disabled={!issues.data.has_more}
            className="rounded-lg border border-line px-3 py-1.5 text-slate-300 hover:bg-panel2 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

function IssuesBody({
  reposLoading,
  selectedRepo,
  issuesLoading,
  issuesError,
  issues,
  solvingIssue,
  onSolve,
}: {
  reposLoading: boolean;
  selectedRepo: Repository | undefined;
  issuesLoading: boolean;
  issuesError: unknown;
  issues: GitHubIssue[];
  solvingIssue: number | null;
  onSolve: (issue: GitHubIssue) => void;
}) {
  if (reposLoading) {
    return <div className="rounded-xl border border-line bg-panel p-8 text-center text-sm text-slate-500">Loading repositories…</div>;
  }
  if (!selectedRepo) {
    return <div className="rounded-xl border border-line bg-panel p-8 text-center text-sm text-slate-500">Connect and index a repository first.</div>;
  }
  if (issuesLoading) {
    return (
      <div className="rounded-xl border border-line bg-panel p-8 text-center text-sm text-slate-500">
        <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin" />
        Fetching GitHub issues…
      </div>
    );
  }
  if (issuesError) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-5 text-sm text-red-200">
        Could not fetch GitHub issues. Check `GITHUB_PAT`, repository access, or GitHub rate limits.
      </div>
    );
  }
  if (issues.length === 0) {
    return <div className="rounded-xl border border-line bg-panel p-8 text-center text-sm text-slate-500">No matching issues found.</div>;
  }

  return (
    <div className="space-y-3">
      {issues.map((issue) => (
        <div key={issue.number} className="rounded-xl border border-line bg-panel p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-panel2 px-2 py-0.5 text-xs text-slate-400">#{issue.number}</span>
                <span className="text-xs uppercase tracking-wide text-green-400">{issue.state}</span>
                {issue.author && <span className="text-xs text-slate-500">by {issue.author}</span>}
              </div>
              <h2 className="break-words text-base font-medium text-slate-100">{issue.title}</h2>
              {issue.body && <p className="mt-2 line-clamp-3 whitespace-pre-wrap break-words text-sm text-slate-500">{issue.body}</p>}
              {issue.labels.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {issue.labels.map((label) => (
                    <span key={label.name} className="rounded-full border border-line px-2 py-0.5 text-xs text-slate-400">
                      {label.name}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <a
                href={issue.html_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-xs text-slate-300 hover:bg-panel2"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                GitHub
              </a>
              <button
                onClick={() => onSolve(issue)}
                disabled={selectedRepo.index_status !== "READY" || solvingIssue === issue.number}
                className="inline-flex items-center gap-1.5 rounded-lg bg-green-500/15 px-3 py-2 text-xs text-green-300 disabled:opacity-50"
              >
                {solvingIssue === issue.number ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                Solve
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
