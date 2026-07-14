import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Plus, FolderGit2 } from "lucide-react";
import { useRepositories, connectRepository, reindexRepository, triggerManualRun } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";

export function Repositories() {
  const { data: repos, isLoading } = useRepositories();
  const qc = useQueryClient();
  const [owner, setOwner] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  async function connect() {
    if (!owner || !name) return;
    setBusy(true);
    try {
      await connectRepository(owner.trim(), name.trim());
      setOwner("");
      setName("");
      qc.invalidateQueries({ queryKey: ["repositories"] });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-slate-100">Repositories</h1>

      <div className="rounded-xl border border-line bg-panel p-5">
        <h3 className="mb-3 text-sm font-medium text-slate-300">Connect a repository</h3>
        <div className="flex flex-wrap items-center gap-3">
          <input
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
            placeholder="owner"
            className="rounded-lg border border-line bg-ink px-3 py-2 text-sm text-slate-200"
          />
          <span className="text-slate-500">/</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="repo"
            className="rounded-lg border border-line bg-ink px-3 py-2 text-sm text-slate-200"
          />
          <button
            onClick={connect}
            disabled={busy}
            className="flex items-center gap-2 rounded-lg bg-blue-500/20 px-4 py-2 text-sm text-blue-300 disabled:opacity-50"
          >
            <Plus className="h-4 w-4" /> Connect & index
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {isLoading && <div className="text-slate-500">Loading…</div>}
        {repos?.map((r) => (
          <div key={r.id} className="flex items-center justify-between rounded-xl border border-line bg-panel p-5">
            <div className="flex items-center gap-3">
              <FolderGit2 className="h-5 w-5 text-slate-500" />
              <div>
                <div className="text-sm text-slate-200">{r.owner}/{r.name}</div>
                <div className="text-xs text-slate-500">
                  {r.files_indexed} files indexed
                  {r.last_indexed_sha ? ` · ${r.last_indexed_sha.slice(0, 7)}` : ""}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge status={r.index_status} />
              <button
                onClick={() => reindexRepository(r.id)}
                className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs text-slate-300 hover:bg-panel2"
              >
                <RefreshCw className="h-3.5 w-3.5" /> Re-index
              </button>
              <ManualTrigger repoId={r.id} />
            </div>
          </div>
        ))}
        {repos && repos.length === 0 && (
          <div className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-slate-500">
            No repositories connected yet.
          </div>
        )}
      </div>
    </div>
  );
}

function ManualTrigger({ repoId }: { repoId: string }) {
  const [num, setNum] = useState("");
  return (
    <div className="flex items-center gap-2">
      <input
        value={num}
        onChange={(e) => setNum(e.target.value)}
        placeholder="issue #"
        className="w-20 rounded-lg border border-line bg-ink px-2 py-1.5 text-xs text-slate-200"
      />
      <button
        onClick={() => num && triggerManualRun(repoId, parseInt(num, 10))}
        className="rounded-lg bg-green-500/15 px-3 py-1.5 text-xs text-green-300"
      >
        Run
      </button>
    </div>
  );
}
