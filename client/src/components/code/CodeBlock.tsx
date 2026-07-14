export function CodeBlock({ code, label }: { code: string; label?: string }) {
  return (
    <div className="overflow-hidden rounded-lg border border-line bg-ink">
      {label && (
        <div className="border-b border-line px-3 py-1.5 text-[11px] uppercase tracking-wide text-slate-500">
          {label}
        </div>
      )}
      <pre className="max-h-80 overflow-auto p-3 text-xs leading-relaxed text-slate-300">
        <code>{code}</code>
      </pre>
    </div>
  );
}
