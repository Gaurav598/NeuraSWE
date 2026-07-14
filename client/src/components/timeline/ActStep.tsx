import { motion } from "framer-motion";
import { Wrench } from "lucide-react";

export function ActStep({ tool, args }: { tool: string; args?: Record<string, any> | null }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="min-w-0 rounded-lg border border-green-500/30 bg-green-500/5 p-4"
    >
      <div className="mb-1.5 flex items-center gap-2 text-xs font-medium text-green-300">
        <Wrench className="h-4 w-4" />
        ACT · <span className="font-mono">{tool}</span>
      </div>
      {args && Object.keys(args).length > 0 && (
        <pre className="mt-1 max-w-full overflow-auto rounded bg-ink p-2 text-xs text-slate-300">
          {JSON.stringify(args, null, 2)}
        </pre>
      )}
    </motion.div>
  );
}
