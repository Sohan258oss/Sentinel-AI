import type { AgentLiveState } from "../hooks/useIncidentRun";
import { AGENT_LABEL, AGENT_SDG, formatPercent } from "../lib/format";
import type { AgentRole, AgentTrace } from "../lib/types";

interface Props {
  role: AgentRole | null;
  agentState: AgentLiveState | null;
  traces: AgentTrace[];
  onClose: () => void;
  minimized: boolean;
  onMinimize: () => void;
  onRestore: () => void;
}

const SDG_DETAILS: Partial<Record<AgentRole, { title: string; desc: string; icon: string }>> = {
  medical:        { title: "SDG 3: Good Health & Well-Being",           desc: "Ensures emergency triage, ICU bed availability, and medical supply routing.",            icon: "🏥" },
  infrastructure: { title: "SDG 9: Industry, Innovation & Infrastructure", desc: "Monitors transit bridge structural safety, road inundation, and power grid stability.", icon: "🏗️" },
  shelter:        { title: "SDG 11: Sustainable Cities & Communities",   desc: "Assesses relief camp capacity, flood safety zones, and displacement support.",          icon: "⛺" },
  weather:        { title: "SDG 13: Climate Action",                     desc: "Processes radar hydrology, extreme precipitation forecasts, and storm tracks.",           icon: "🌦️" },
  allocation:     { title: "SDG 17: Partnerships for the Goals",         desc: "Optimizes multi-depot emergency supply distribution and humanitarian logistics.",         icon: "🚛" },
};

const AGENT_DESCRIPTIONS: Record<AgentRole, string> = {
  intake:            "Synthesizes incoming emergency SOS dispatches, satellite telemetry, and field reports.",
  situation_analysis:"Establishes baseline incident scope, population at risk, and cascading hazards.",
  commander:         "Determines primary response strategy and dispatches relevant specialist agents.",
  weather:           "Evaluates precipitation, storm surge, river gauge levels, and atmospheric forecasts.",
  infrastructure:    "Assesses transport corridors, bridge integrity, power grids, and critical facilities.",
  medical:           "Coordinates hospital bed capacity, trauma centers, ambulances, and medical supplies.",
  shelter:           "Evaluates evacuation shelter capacities, flood safety ratings, and relief supplies.",
  knowledge:         "Queries national disaster management guidelines (NDMA/FEMA) via RAG doctrine search.",
  logistics:         "Manages warehouse inventories, transport fleet readiness, and supply chains.",
  volunteer:         "Mobilizes local first-responder networks and community rescue teams.",
  allocation:        "Runs linear optimization to pair supply depots with affected zones minimizing ETA.",
  resource_allocation: "Optimizes allocation of emergency boats, water pumps, tents, and relief rations.",
  news:              "Retrieves live open-source intelligence and news reports to corroborate field telemetry.",
  reflection:        "Performs autonomous self-audit, checking logic for unmet needs or doctrine violations.",
  communication:     "Generates public emergency alert bulletins and inter-agency coordination briefs.",
};

const STATUS_COLOR: Record<string, string> = {
  running: "#22d3ee", dispatched: "#0891b2", completed: "#4ade80",
  degraded: "#facc15", failed: "#ef4444", skipped: "#64748b", idle: "#64748b",
};

export function AgentInspectorModal({ role, agentState, traces, onClose, minimized, onMinimize, onRestore }: Props) {
  if (!role) return null;

  const agentTraces = traces.filter((t) => t.agent === role);
  const sdg         = SDG_DETAILS[role];
  const label       = AGENT_LABEL[role];
  const description = AGENT_DESCRIPTIONS[role];
  const status      = agentState?.status ?? "idle";
  const color       = STATUS_COLOR[status] ?? "#22d3ee";

  // ── Minimized pill ── bottom-left, always visible when role is set ──
  if (minimized) {
    return (
      <div className="fixed bottom-14 left-4 z-50">
        <button
          onClick={onRestore}
          className="group flex items-center gap-2 rounded-full border border-edge-bright bg-panel/95 px-3 py-1.5 font-mono text-[10px] font-bold shadow-2xl backdrop-blur-md transition-all hover:border-signal hover:text-signal"
        >
          <span className="size-2 shrink-0 rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
          <span className="uppercase tracking-wider text-ink">{label}</span>
          <span className="rounded px-1.5 py-0.5 text-[8.5px] uppercase font-bold" style={{ background: `${color}20`, color, border: `1px solid ${color}40` }}>{status}</span>
          <span className="text-ink-faint group-hover:text-signal">▲</span>
        </button>
      </div>
    );
  }

  // ── Full card ────────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/80 p-4 backdrop-blur-md">
      <div className="w-full max-w-lg rounded-xl border border-edge-bright bg-panel/95 p-5 shadow-2xl">

        {/* ── Header ─────────────────────────────────────────────── */}
        <div className="flex items-center justify-between border-b border-edge/80 pb-3">
          <div className="flex items-center gap-2.5">
            <span className="size-3 rounded-full pulse-ring" style={{ background: color }} />
            <div>
              <h2 className="font-mono text-sm font-bold uppercase tracking-wider text-ink">{label}</h2>
              <p className="font-mono text-[10px] text-ink-faint">ROLE TELEMETRY & REASONING AUDIT</p>
            </div>
          </div>

          {/* Minimize (─) and Close (✕) */}
          <div className="flex items-center gap-1">
            <button
              onClick={onMinimize}
              title="Minimize"
              className="flex h-7 w-7 items-center justify-center rounded font-mono text-base leading-none text-ink-faint hover:bg-edge hover:text-ink transition-colors"
            >
              ─
            </button>
            <button
              onClick={onClose}
              title="Close"
              className="flex h-7 w-7 items-center justify-center rounded font-mono text-xs text-ink-faint hover:bg-edge hover:text-ink transition-colors"
            >
              ✕
            </button>
          </div>
        </div>

        {/* ── Body ───────────────────────────────────────────────── */}
        <div className="mt-3.5 space-y-3">

          {/* Status + SDG */}
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-edge/60 bg-abyss/80 p-2.5">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[10px] font-bold uppercase text-ink-faint">Status:</span>
              <span className="rounded px-2 py-0.5 font-mono text-[10px] font-bold uppercase"
                style={{ background: `${color}20`, color, border: `1px solid ${color}40` }}>
                {status}
              </span>
            </div>
            {sdg && (
              <span className="flex items-center gap-1 rounded border border-signal/30 bg-signal/10 px-2 py-0.5 font-mono text-[10px] font-bold text-signal">
                {sdg.icon} {AGENT_SDG[role]}
              </span>
            )}
          </div>

          {/* Description */}
          <div className="rounded-lg border border-edge/60 bg-panel/60 p-2.5">
            <p className="text-[11px] leading-relaxed text-ink-dim">{description}</p>
            {sdg && (
              <div className="mt-2 border-t border-edge/40 pt-1.5 font-mono text-[10px] text-signal-deep">
                <span className="font-bold">{sdg.title}</span> — {sdg.desc}
              </div>
            )}
          </div>

          {/* Metrics */}
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: "Confidence", value: agentState?.confidence ? formatPercent(agentState.confidence) : "—", cls: "text-emerald-400" },
              { label: "Latency",    value: agentState?.latencyMs   ? `${agentState.latencyMs}ms`            : "—", cls: "text-ink"        },
              { label: "Tool Calls", value: String(agentState?.toolCalls ?? 0),                                     cls: "text-signal"     },
            ].map(({ label: l, value, cls }) => (
              <div key={l} className="rounded-lg border border-edge/60 bg-abyss/60 p-2">
                <span className="block font-mono text-[9px] uppercase text-ink-faint">{l}</span>
                <span className={`font-mono text-sm font-bold ${cls}`}>{value}</span>
              </div>
            ))}
          </div>

          {/* Trace log */}
          <div>
            <h3 className="mb-1.5 font-mono text-[10px] font-bold uppercase tracking-wider text-ink-dim">
              Execution Traces ({agentTraces.length})
            </h3>
            <div className="max-h-[140px] space-y-1 overflow-y-auto rounded-lg border border-edge/60 bg-abyss/90 p-2">
              {agentTraces.length === 0 ? (
                <p className="py-4 text-center font-mono text-[10px] text-ink-faint">No traces logged yet.</p>
              ) : (
                agentTraces.map((trace) => (
                  <div key={trace.event_id} className="rounded border border-edge/40 bg-panel/40 p-1.5">
                    <div className="flex items-center justify-between font-mono text-[9px] text-ink-faint">
                      <span className="font-semibold text-signal">{trace.event_type.toUpperCase()}</span>
                      <span>{new Date(trace.timestamp).toLocaleTimeString()}</span>
                    </div>
                    <p className="mt-0.5 text-[10.5px] font-medium text-ink">{trace.title}</p>
                    {trace.detail && <p className="mt-0.5 line-clamp-2 text-[10px] text-ink-dim">{trace.detail}</p>}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* ── Footer ─────────────────────────────────────────────── */}
        <div className="mt-4 flex items-center justify-end border-t border-edge/60 pt-3">
          <button
            onClick={onClose}
            className="rounded-md bg-signal px-4 py-1.5 font-mono text-xs font-bold text-void shadow-md transition-all hover:bg-signal-deep"
          >
            Close Inspector
          </button>
        </div>

      </div>
    </div>
  );
}
