/**
 * Lightweight unified-diff renderer. Avoids a heavy dependency by colorizing
 * raw `git diff` text line-by-line.
 */
export function DiffViewer({ diff }: { diff: string }) {
  if (!diff || diff === "No changes yet.") {
    return <div className="text-sm text-slate-500">No changes yet.</div>;
  }
  const lines = diff.split("\n");
  return (
    <div className="max-h-[70vh] overflow-auto rounded-lg border border-line bg-ink font-mono text-xs">
      {lines.map((line, i) => {
        let cls = "text-slate-400";
        if (line.startsWith("+") && !line.startsWith("+++")) cls = "bg-green-500/10 text-green-300";
        else if (line.startsWith("-") && !line.startsWith("---")) cls = "bg-red-500/10 text-red-300";
        else if (line.startsWith("@@")) cls = "text-blue-300";
        else if (line.startsWith("diff ") || line.startsWith("index ")) cls = "text-slate-500";
        return (
          <div key={i} className={`min-w-max whitespace-pre px-3 ${cls}`}>
            {line || " "}
          </div>
        );
      })}
    </div>
  );
}
