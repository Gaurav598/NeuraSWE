import { motion } from "framer-motion";
import { Brain } from "lucide-react";

export function ThinkStep({ step, thought }: { step?: number; thought: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="min-w-0 rounded-lg border border-blue-500/30 bg-blue-500/5 p-4"
    >
      <div className="mb-1.5 flex items-center gap-2 text-xs font-medium text-blue-300">
        <Brain className="h-4 w-4" />
        THINK {step != null && <span className="text-blue-500/70">· step {step}</span>}
      </div>
      <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-200">{thought}</p>
    </motion.div>
  );
}
