import type {
  AgentTrace,
  OperationalPicture,
  RegistryResponse,
  RunAccepted,
  Scenario,
  SystemStatus,
} from "./types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(`${response.status} ${path}: ${detail.slice(0, 200)}`);
  }
  return (await response.json()) as T;
}

export const api = {
  systemStatus: () => request<SystemStatus>("/system/status"),
  scenarios: () => request<Scenario[]>("/scenarios"),
  runScenario: (key: string) =>
    request<RunAccepted>(`/scenarios/${key}/run`, { method: "POST" }),
  traces: (runId: string) => request<AgentTrace[]>(`/runs/${runId}/traces`),
  registry: (kind: string) => request<RegistryResponse>(`/registry/${kind}`),
  incident: (incidentId: string) =>
    request<{
      run_id: string;
      status: string;
      running: boolean;
      error: string | null;
      picture: OperationalPicture | null;
      metrics: Record<string, number> | null;
    }>(`/incidents/${incidentId}`),
  submitIncident: (payload: Record<string, unknown>) =>
    request<RunAccepted>("/incidents", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

/**
 * Subscribe to a run's live trace feed.
 *
 * Returns a disposer. The `stream_closed` event carries the final operational
 * picture, which saves the client an extra fetch and — more usefully —
 * guarantees the UI and the stream agree about when the run ended.
 */
export function subscribeToRun(
  runId: string,
  handlers: {
    onTrace: (trace: AgentTrace) => void;
    onComplete: (picture: OperationalPicture | null) => void;
    onError?: (message: string) => void;
  },
): () => void {
  const source = new EventSource(`${BASE}/runs/${runId}/stream`);

  const traceEvents: string[] = [
    "node_started",
    "node_completed",
    "node_failed",
    "reasoning",
    "tool_call",
    "tool_result",
    "retrieval",
    "routing_decision",
    "critique",
    "revision",
    "run_started",
    "run_completed",
    "error",
  ];

  for (const name of traceEvents) {
    source.addEventListener(name, (event) => {
      try {
        handlers.onTrace(JSON.parse((event as MessageEvent).data) as AgentTrace);
      } catch {
        /* a malformed frame must not tear down the stream */
      }
    });
  }

  source.addEventListener("stream_closed", (event) => {
    let picture: OperationalPicture | null = null;
    try {
      const parsed = JSON.parse((event as MessageEvent).data);
      if (parsed && !parsed.error) picture = parsed as OperationalPicture;
    } catch {
      /* fall through with null */
    }
    handlers.onComplete(picture);
    source.close();
  });

  source.onerror = () => {
    // EventSource retries on its own; only surface a hard close.
    if (source.readyState === EventSource.CLOSED) {
      handlers.onError?.("Trace stream disconnected");
    }
  };

  return () => source.close();
}
