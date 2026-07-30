import { useState } from "react";
import type { AgentRole } from "../lib/types";

interface Props {
  activeAgents: Record<string, any>;
  traces: any[];
  running: boolean;
  onSelectAgent?: (role: AgentRole) => void;
}

const AGENT_LIST: Array<{ role: AgentRole; label: string; icon: string; desc: string }> = [
  { role: "commander", label: "Commander Agent", icon: "🎖️", desc: "Global strategy & dispatch priority" },
  { role: "situation_analysis", label: "Situation Analysis Agent", icon: "📊", desc: "Triage & casualty assessment" },
  { role: "weather", label: "Weather Agent", icon: "📡", desc: "Live meteorological telemetry" },
  { role: "medical", label: "Medical Agent", icon: "🏥", desc: "Triage, ICU beds & medical dispatch" },
  { role: "shelter", label: "Shelter Agent", icon: "🎪", desc: "Relief camp allocation & water supply" },
  { role: "infrastructure", label: "Infrastructure Agent", icon: "🌉", desc: "Road closures & bridge integrity" },
  { role: "resource_allocation", label: "Resource Allocation Agent", icon: "🚛", desc: "NDRF boats, pumps & ration trucks" },
  { role: "knowledge", label: "Government Knowledge Agent (RAG)", icon: "📚", desc: "NDMA SOPs & WHO guidelines" },
  { role: "news", label: "OSINT News Agent", icon: "📰", desc: "Live Google News & newsapi feed" },
  { role: "reflection", label: "Reflection & Assurance Agent", icon: "🛡️", desc: "Critique & safety validation" },
  { role: "communication", label: "Communication Agent", icon: "📢", desc: "Public alerts & SMS broadcasting" },
];

export function MultiAgentDrawer({ activeAgents, traces, running, onSelectAgent }: Props) {
  const [isOpen, setIsOpen] = useState(true);

  const activeCount = Object.keys(activeAgents).length || (running ? 11 : 0);

  return (
    <div className="rounded-xl border border-signal/40 bg-panel/95 shadow-2xl backdrop-blur-md transition-all">
      {/* Header bar */}
      <div
        onClick={() => setIsOpen((v) => !v)}
        className="flex cursor-pointer items-center justify-between border-b border-edge/60 px-3.5 py-2.5 transition-colors hover:bg-panel-raised"
      >
        <div className="flex items-center gap-2">
          <span className={`size-2.5 rounded-full ${running ? "bg-signal pulse-ring" : "bg-emerald-400"}`} />
          <h3 className="font-mono text-[11px] font-bold uppercase tracking-wider text-signal">
            AEGIS AI — Multi-Agent Intelligence Network ({activeCount} Active)
          </h3>
        </div>

        <div className="flex items-center gap-2 font-mono text-[10px]">
          {running && (
            <span className="rounded bg-signal/20 px-2 py-0.5 font-bold text-signal border border-signal/40">
              GRAPH RUNNING…
            </span>
          )}
          <button className="text-ink-faint hover:text-ink">
            {isOpen ? "▼ Collapse" : "▲ Expand"}
          </button>
        </div>
      </div>

      {/* Expandable Agent Grid */}
      {isOpen && (
        <div className="p-3">
          <p className="font-mono text-[10px] text-ink-faint mb-2.5">
            Transparent multi-agent system executing concurrent reasoning, tool calls, and RAG retrieval:
          </p>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {AGENT_LIST.map((ag) => {
              const state = activeAgents[ag.role];
              const isDone = state?.status === "completed" || traces.some((t) => t.agent === ag.role);
              const isRunningNow = running && (!state || state?.status === "running");

              return (
                <div
                  key={ag.role}
                  onClick={() => onSelectAgent?.(ag.role)}
                  className={`group cursor-pointer rounded-lg border p-2.5 transition-all ${
                    isDone
                      ? "border-emerald-500/40 bg-emerald-500/5 hover:border-emerald-400"
                      : isRunningNow
                      ? "border-signal/60 bg-signal/10 hover:border-signal"
                      : "border-edge/60 bg-abyss/60 hover:border-edge"
                  }`}
                >
                  <div className="flex items-center justify-between gap-1 mb-1">
                    <span className="font-mono text-xs">{ag.icon}</span>
                    <span
                      className={`rounded px-1.5 py-0.2 font-mono text-[8px] font-bold uppercase ${
                        isDone
                          ? "bg-emerald-500/20 text-emerald-300"
                          : isRunningNow
                          ? "bg-signal-deep text-void animate-pulse"
                          : "bg-edge text-ink-faint"
                      }`}
                    >
                      {isDone ? "ACTIVE" : isRunningNow ? "RUNNING" : "READY"}
                    </span>
                  </div>

                  <h4 className="font-mono text-[10.5px] font-bold text-ink truncate group-hover:text-signal">
                    {ag.label}
                  </h4>
                  <p className="mt-0.5 line-clamp-1 font-mono text-[9px] text-ink-faint">
                    {ag.desc}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
