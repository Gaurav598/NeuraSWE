import { useState } from "react";
import { motion } from "framer-motion";
import { Eye, ChevronDown, ChevronRight } from "lucide-react";

export function ObserveStep({ observation }: { observation: string }) {
  const long = observation.length > 400;
  const [open, setOpen] = useState(!long);
  const shown = open ? observation : observation.slice(0, 400) + " …";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="min-w-0 rounded-lg border border-line bg-panel2 p-4"
    >
      <button
        onClick={() => long && setOpen(!open)}
        className="mb-1.5 flex items-center gap-2 text-xs font-medium text-slate-400"
      >
        <Eye className="h-4 w-4" />
        OBSERVE
        {long && (open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />)}
      </button>
      <pre className="max-w-full overflow-auto whitespace-pre-wrap break-words text-xs leading-relaxed text-slate-300">
        {shown}
      </pre>
    </motion.div>
  );
}
