import { FileCode2 } from "lucide-react";

export function FileTree({ files }: { files: string[] }) {
  if (files.length === 0) {
    return <div className="text-sm text-slate-500">No files touched yet.</div>;
  }
  return (
    <ul className="space-y-1">
      {files.map((f) => (
        <li key={f} className="flex min-w-0 items-start gap-2 text-sm text-slate-300">
          <FileCode2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500" />
          <span className="break-all font-mono text-xs leading-relaxed">{f}</span>
        </li>
      ))}
    </ul>
  );
}
