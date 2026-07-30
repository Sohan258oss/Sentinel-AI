import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, subscribeToRun } from "../lib/api";
import type {
  AgentRole,
  AgentStatus,
  AgentTrace,
  OperationalPicture,
} from "../lib/types";

export interface AgentLiveState {
  role: AgentRole;
  status: AgentStatus;
  lastTitle: string;
  toolCalls: number;
  confidence: number | null;
  latencyMs: number | null;
  degraded: boolean;
}

export interface RunState {
  runId: string | null;
  incidentId: string | null;
  traces: AgentTrace[];
  agents: Record<string, AgentLiveState>;
  picture: OperationalPicture | null;
  running: boolean;
  error: string | null;
}

const EMPTY: RunState = {
  runId: null,
  incidentId: null,
  traces: [],
  agents: {},
  picture: null,
  running: false,
  error: null,
};

/**
 * Reduces the raw trace stream into per-agent live state.
 *
 * Derived rather than stored: the backend never sends an "agent status" object,
 * so the UI computes it from the event sequence. That keeps the wire format
 * small and means a replayed stream reconstructs identical state.
 */
function reduceAgents(traces: AgentTrace[]): Record<string, AgentLiveState> {
  const agents: Record<string, AgentLiveState> = {};

  const ensure = (role: AgentRole): AgentLiveState => {
    if (!agents[role]) {
      agents[role] = {
        role,
        status: "idle",
        lastTitle: "",
        toolCalls: 0,
        confidence: null,
        latencyMs: null,
        degraded: false,
      };
    }
    return agents[role];
  };

  for (const trace of traces) {
    const agent = ensure(trace.agent);

    switch (trace.event_type) {
      case "node_started":
        agent.status = "running";
        agent.lastTitle = trace.title;
        break;
      case "tool_call":
        agent.toolCalls += 1;
        agent.status = "running";
        break;
      case "node_completed":
        agent.status = trace.status === "degraded" ? "degraded" : "completed";
        agent.lastTitle = trace.title;
        agent.confidence = trace.confidence ?? agent.confidence;
        agent.latencyMs = trace.latency_ms ?? agent.latencyMs;
        break;
      case "node_failed":
      case "error":
        agent.status = "failed";
        agent.lastTitle = trace.title;
        break;
      case "reasoning":
        if (trace.status === "degraded") agent.degraded = true;
        break;
      case "routing_decision": {
        // The commander's decision pre-marks the chosen specialists as
        // dispatched, so the UI shows the fan-out an instant before those
        // nodes actually begin — which is what makes the branch legible.
        const activated = (trace.payload?.activated as string[]) ?? [];
        for (const role of activated) {
          const target = ensure(role as AgentRole);
          if (target.status === "idle") target.status = "dispatched";
        }
        const declined =
          (trace.payload?.declined as { agent: string }[] | undefined) ?? [];
        for (const entry of declined) {
          const target = ensure(entry.agent as AgentRole);
          if (target.status === "idle") target.status = "skipped";
        }
        break;
      }
      default:
        break;
    }
  }

  return agents;
}

export function useIncidentRun() {
  const [state, setState] = useState<RunState>(EMPTY);
  const disposer = useRef<(() => void) | null>(null);

  useEffect(() => () => disposer.current?.(), []);

  const subscribeRun = useCallback((accepted: { run_id: string; incident_id: string }) => {
    disposer.current?.();
    setState({ ...EMPTY, running: true, runId: accepted.run_id, incidentId: accepted.incident_id });

    disposer.current = subscribeToRun(accepted.run_id, {
      onTrace: (trace) =>
        setState((previous) => {
          if (previous.traces.some((t) => t.event_id === trace.event_id)) {
            return previous;
          }
          const traces = [...previous.traces, trace].sort(
            (a, b) => a.sequence - b.sequence,
          );
          return { ...previous, traces, agents: reduceAgents(traces) };
        }),
      onComplete: async (picture) => {
        if (picture) {
          setState((previous) => ({ ...previous, picture, running: false }));
          return;
        }
        setState((previous) => ({ ...previous, running: false }));
        try {
          const incidentId = accepted.incident_id;
          const detail = await api.incident(incidentId);
          setState((previous) => ({ ...previous, picture: detail.picture }));
        } catch {
          /* leave picture null; the UI shows the trace timeline regardless */
        }
      },
      onError: (message) =>
        setState((previous) => ({ ...previous, error: message })),
    });
  }, []);

  const start = useCallback(async (scenarioKey: string) => {
    disposer.current?.();
    setState({ ...EMPTY, running: true });

    try {
      const accepted = await api.runScenario(scenarioKey);
      subscribeRun(accepted);
    } catch (error) {
      setState({
        ...EMPTY,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }, [subscribeRun]);

  const startCustom = useCallback(async (payload: Record<string, unknown>) => {
    disposer.current?.();
    setState({ ...EMPTY, running: true });

    try {
      const accepted = await api.submitIncident(payload);
      subscribeRun(accepted);
    } catch (error) {
      setState({
        ...EMPTY,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }, [subscribeRun]);

  const reset = useCallback(() => {
    disposer.current?.();
    setState(EMPTY);
  }, []);

  const stats = useMemo(() => {
    const toolCalls = state.traces.filter(
      (t) => t.event_type === "tool_call",
    ).length;
    const retrievals = state.traces.filter(
      (t) => t.event_type === "retrieval",
    ).length;
    const critiques = state.traces.filter(
      (t) => t.event_type === "critique",
    ).length;
    const fallbacks = state.traces.filter(
      (t) => t.tool_invocation?.used_fallback,
    ).length;
    const activeAgents = Object.values(state.agents).filter((a) =>
      ["running", "completed", "degraded"].includes(a.status),
    ).length;
    return { toolCalls, retrievals, critiques, fallbacks, activeAgents };
  }, [state.traces, state.agents]);

  return { ...state, stats, start, startCustom, reset };
}
