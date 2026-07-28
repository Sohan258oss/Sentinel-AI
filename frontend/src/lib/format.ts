import type { AgentRole, Severity, TraceEventType } from "./types";

export const SEVERITY_COLOR: Record<Severity, string> = {
  informational: "#38bdf8",
  minor: "#4ade80",
  moderate: "#facc15",
  severe: "#fb923c",
  catastrophic: "#ef4444",
};

export const SEVERITY_RANK: Record<Severity, number> = {
  informational: 0,
  minor: 1,
  moderate: 2,
  severe: 3,
  catastrophic: 4,
};

/** Display order matches the graph's execution order, not the alphabet. */
export const AGENT_ORDER: AgentRole[] = [
  "intake",
  "situation_analysis",
  "commander",
  "weather",
  "infrastructure",
  "medical",
  "shelter",
  "knowledge",
  "allocation",
  "reflection",
  "communication",
];

export const AGENT_LABEL: Record<AgentRole, string> = {
  intake: "Intake",
  situation_analysis: "Situation Analysis",
  commander: "Incident Commander",
  weather: "Weather & Climate",
  infrastructure: "Infrastructure",
  medical: "Medical Coordination",
  shelter: "Shelter & Evacuation",
  knowledge: "Doctrine (RAG)",
  logistics: "Logistics",
  volunteer: "Volunteers",
  allocation: "Resource Allocation",
  reflection: "Reflection",
  communication: "Communication",
};

export const AGENT_GLYPH: Record<AgentRole, string> = {
  intake: "IN",
  situation_analysis: "SA",
  commander: "CC",
  weather: "WX",
  infrastructure: "IF",
  medical: "MD",
  shelter: "SH",
  knowledge: "KB",
  logistics: "LG",
  volunteer: "VL",
  allocation: "RA",
  reflection: "RF",
  communication: "CM",
};

/** Which SDG each agent primarily serves — surfaced in the UI. */
export const AGENT_SDG: Partial<Record<AgentRole, string>> = {
  medical: "SDG 3",
  infrastructure: "SDG 9",
  shelter: "SDG 11",
  weather: "SDG 13",
  allocation: "SDG 17",
};

export const EVENT_STYLE: Record<
  TraceEventType,
  { glyph: string; color: string; label: string }
> = {
  run_started: { glyph: "◆", color: "#22d3ee", label: "RUN" },
  run_completed: { glyph: "◆", color: "#22d3ee", label: "RUN" },
  node_started: { glyph: "▶", color: "#22d3ee", label: "START" },
  node_completed: { glyph: "✓", color: "#4ade80", label: "DONE" },
  node_failed: { glyph: "✕", color: "#ef4444", label: "FAIL" },
  reasoning: { glyph: "◇", color: "#94a3bd", label: "THINK" },
  tool_call: { glyph: "→", color: "#818cf8", label: "TOOL" },
  tool_result: { glyph: "←", color: "#6366f1", label: "DATA" },
  retrieval: { glyph: "▤", color: "#a78bfa", label: "RAG" },
  routing_decision: { glyph: "⑂", color: "#facc15", label: "ROUTE" },
  critique: { glyph: "!", color: "#fb923c", label: "AUDIT" },
  revision: { glyph: "↻", color: "#fb923c", label: "REVISE" },
  error: { glyph: "✕", color: "#ef4444", label: "ERROR" },
};

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-IN").format(Math.round(value));
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

export function titleCase(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function clockTime(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleTimeString("en-GB", { hour12: false });
}

export function relativeDuration(from: string, to?: string | null): string {
  if (!to) return "—";
  const seconds = (new Date(to).getTime() - new Date(from).getTime()) / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}
