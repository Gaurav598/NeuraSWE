import { Fragment } from "react";
import type { Step, LiveStep } from "../../types";
import { ActStep } from "./ActStep";
import { ObserveStep } from "./ObserveStep";
import { StepConnector } from "./StepConnector";

/**
 * Renders a unified timeline from persisted steps (historical) merged with any
 * live events streamed over the socket. Live events that go beyond the persisted
 * set are appended so the user sees the agent working in real time.
 */
export function ReasoningTimeline({
  steps,
  live,
}: {
  steps: Step[];
  live: LiveStep[];
}) {
  const persistedMax = steps.length ? Math.max(...steps.map((s) => s.step_number)) : 0;

  // Only operational actions are shown; private model reasoning is never rendered.
  const inflight = live.filter(
    (e) => (e.step ?? 0) > persistedMax && e.type === "act"
  );

  return (
    <div className="space-y-2">
      {steps.map((s, idx) => (
        <Fragment key={s.id}>
          {s.tool_name && (
            <>
              <StepConnector />
              <ActStep tool={s.tool_name} args={s.tool_args} />
            </>
          )}
          {s.observation && (
            <>
              <StepConnector />
              <ObserveStep observation={s.observation} />
            </>
          )}
          {idx < steps.length - 1 && <StepConnector />}
        </Fragment>
      ))}

      {inflight.length > 0 && <StepConnector />}
      {inflight.map((e, i) => (
        <Fragment key={`live-${i}`}>
          {e.type === "act" && e.tool && (
            <>
              <StepConnector />
              <ActStep tool={e.tool} args={e.args} />
            </>
          )}
        </Fragment>
      ))}

      {steps.length === 0 && inflight.length === 0 && (
        <div className="rounded-lg border border-dashed border-line p-8 text-center text-sm text-slate-500">
          Waiting for operational events…
        </div>
      )}
    </div>
  );
}
