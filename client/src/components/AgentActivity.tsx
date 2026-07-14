import { Bot, CheckCircle2, CircleDashed, Loader2 } from "lucide-react";
import type { LiveStep, Step } from "../types";

const AGENTS = ["Planner", "Researcher", "Coder", "Tester", "Reviewer", "PR Agent"];

type AgentState = {
  name: string;
  status: "waiting" | "executing" | "complete";
  detail: string;
};

export function AgentActivity({ steps, live }: { steps: Step[]; live: LiveStep[] }) {
  const states = buildAgentStates(steps, live);
  return (
    <div className="rounded-xl border border-line bg-panel p-5">
      <div className="mb-4 flex items-center gap-2">
        <Bot className="h-4 w-4 text-blue-300" />
        <h3 className="text-sm font-medium text-slate-300">Multi-agent activity</h3>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {states.map((agent) => (
          <div key={agent.name} className="rounded-lg border border-line bg-panel2/30 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-slate-200">{agent.name}</span>
              <StatusIcon status={agent.status} />
            </div>
            <div className="text-xs capitalize text-slate-500">{agent.status}</div>
            <div className="mt-1 line-clamp-2 min-h-8 break-words text-xs text-slate-400">
              {agent.detail}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function buildAgentStates(steps: Step[], live: LiveStep[]): AgentState[] {
  const states = new Map<string, AgentState>(
    AGENTS.map((name) => [name, { name, status: "waiting", detail: "Waiting for assigned work." }])
  );

  for (const step of steps) {
    const name = step.agent_name || agentForTool(step.tool_name);
    const state = states.get(name);
    if (!state) continue;
    state.status = "complete";
    state.detail = detailForStep(step);
  }

  for (const event of live) {
    const name = event.agent_name || agentForTool(event.tool);
    const state = states.get(name);
    if (!state) continue;
    if (event.type === "observe" || event.type === "done") {
      state.status = "complete";
    } else {
      state.status = "executing";
    }
    state.detail = detailForEvent(event);
  }

  return AGENTS.map((name) => states.get(name)!);
}

function StatusIcon({ status }: { status: AgentState["status"] }) {
  if (status === "complete") return <CheckCircle2 className="h-4 w-4 text-green-400" />;
  if (status === "executing") return <Loader2 className="h-4 w-4 animate-spin text-blue-300" />;
  return <CircleDashed className="h-4 w-4 text-slate-600" />;
}

function detailForStep(step: Step): string {
  if (step.tool_name) return `${labelForTool(step.tool_name)} completed.`;
  return step.thought || "Step completed.";
}

function detailForEvent(event: LiveStep): string {
  if (event.type === "think") return event.thought || "Thinking through the next action.";
  if (event.type === "act" && event.tool) return `${labelForTool(event.tool)} in progress.`;
  if (event.type === "creating_pr") return "Creating pull request.";
  if (event.type === "done") return event.observation || "Done.";
  if (event.type === "setup") return "Preparing sandbox and baseline tests.";
  if (event.type === "observe" && event.tool) return `${labelForTool(event.tool)} completed.`;
  return event.observation || "Working.";
}

function agentForTool(tool?: string | null): string {
  if (!tool) return "Planner";
  if (["search_code", "grep", "read_file"].includes(tool)) return "Researcher";
  if (["edit_file", "create_file", "run_command"].includes(tool)) return "Coder";
  if (tool === "run_tests") return "Tester";
  if (tool === "git_diff") return "Reviewer";
  if (tool === "submit_solution") return "PR Agent";
  return "Planner";
}

function labelForTool(tool: string): string {
  return tool.replace(/_/g, " ");
}
