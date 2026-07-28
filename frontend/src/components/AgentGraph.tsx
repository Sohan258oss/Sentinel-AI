import type { AgentLiveState } from "../hooks/useIncidentRun";
import { AGENT_GLYPH, AGENT_LABEL, AGENT_SDG } from "../lib/format";
import type { AgentRole, AgentStatus } from "../lib/types";

/**
 * Live rendering of the Pattern 5 graph topology.
 *
 * This is the diagram the architecture doc describes, except it is wired to
 * the real trace stream — nodes light up as their agent executes and the
 * conditional fan-out is visible as it happens. Showing the branch actually
 * branching is far more convincing than asserting that it does.
 */

const SPECIALISTS: AgentRole[] = [
  "weather",
  "infrastructure",
  "medical",
  "shelter",
  "knowledge",
];

const STATUS_COLOR: Record<AgentStatus, string> = {
  idle: "#2a3752",
  dispatched: "#0891b2",
  running: "#22d3ee",
  completed: "#4ade80",
  degraded: "#facc15",
  failed: "#ef4444",
  skipped: "#1b2438",
};

const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  intake: { x: 170, y: 26 },
  situation_analysis: { x: 170, y: 88 },
  commander: { x: 170, y: 152 },
  weather: { x: 30, y: 244 },
  infrastructure: { x: 100, y: 244 },
  medical: { x: 170, y: 244 },
  shelter: { x: 240, y: 244 },
  knowledge: { x: 310, y: 244 },
  allocation: { x: 170, y: 340 },
  reflection: { x: 170, y: 408 },
  communication: { x: 170, y: 480 },
};

interface Props {
  agents: Record<string, AgentLiveState>;
  onSelect?: (role: AgentRole) => void;
  selected?: AgentRole | null;
}

function statusOf(
  agents: Record<string, AgentLiveState>,
  role: AgentRole,
): AgentStatus {
  return agents[role]?.status ?? "idle";
}

function isLive(status: AgentStatus): boolean {
  return status === "running" || status === "dispatched";
}

function edgeColor(from: AgentStatus, to: AgentStatus): string {
  if (isLive(to)) return "#22d3ee";
  if (from === "completed" || from === "degraded") {
    return to === "idle" ? "#2a3752" : "#4ade80";
  }
  return "#1b2438";
}

export function AgentGraph({ agents, onSelect, selected }: Props) {
  const node = (role: AgentRole, radius = 15) => {
    const position = NODE_POSITIONS[role];
    const status = statusOf(agents, role);
    const color = STATUS_COLOR[status];
    const live = isLive(status);
    const state = agents[role];
    const isSelected = selected === role;

    return (
      <g
        key={role}
        transform={`translate(${position.x}, ${position.y})`}
        onClick={() => onSelect?.(role)}
        className="cursor-pointer"
      >
        <title>
          {AGENT_LABEL[role]}
          {state?.lastTitle ? ` — ${state.lastTitle}` : ""}
          {status === "skipped" ? " (not activated)" : ""}
        </title>

        {live && (
          <circle
            r={radius + 7}
            fill="none"
            stroke={color}
            strokeWidth="1"
            opacity="0.35"
          >
            <animate
              attributeName="r"
              values={`${radius};${radius + 11};${radius}`}
              dur="1.8s"
              repeatCount="indefinite"
            />
            <animate
              attributeName="opacity"
              values="0.5;0;0.5"
              dur="1.8s"
              repeatCount="indefinite"
            />
          </circle>
        )}

        {isSelected && (
          <circle
            r={radius + 4}
            fill="none"
            stroke="#e8edf7"
            strokeWidth="1"
            strokeDasharray="2 2"
          />
        )}

        <circle
          r={radius}
          fill={status === "idle" || status === "skipped" ? "#0c1120" : "#111829"}
          stroke={color}
          strokeWidth={live ? 2 : 1.5}
          opacity={status === "skipped" ? 0.4 : 1}
        />

        <text
          textAnchor="middle"
          dy="3.5"
          fontSize="9"
          fontFamily="var(--font-mono)"
          fontWeight="600"
          fill={status === "idle" || status === "skipped" ? "#5c6a85" : color}
        >
          {AGENT_GLYPH[role]}
        </text>

        {status === "skipped" && (
          <line
            x1={-radius}
            y1={radius}
            x2={radius}
            y2={-radius}
            stroke="#5c6a85"
            strokeWidth="1"
            opacity="0.6"
          />
        )}
      </g>
    );
  };

  const commanderStatus = statusOf(agents, "commander");
  const allocationStatus = statusOf(agents, "allocation");
  const reflectionStatus = statusOf(agents, "reflection");

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-baseline justify-between px-1">
        <h2 className="font-mono text-[10px] tracking-[0.18em] text-ink-dim">
          AGENT GRAPH
        </h2>
        <span className="font-mono text-[9px] text-ink-faint">
          PATTERN 5 · HYBRID BRANCHING
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <svg
          viewBox="0 0 340 510"
          className="w-full"
          style={{ maxHeight: "100%" }}
        >
          <defs>
            <marker
              id="arrow"
              viewBox="0 0 8 8"
              refX="7"
              refY="4"
              markerWidth="5"
              markerHeight="5"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 7 4 L 0 7 z" fill="currentColor" />
            </marker>
          </defs>

          {/* Sequential spine */}
          <line
            x1="170"
            y1="41"
            x2="170"
            y2="73"
            stroke={edgeColor(
              statusOf(agents, "intake"),
              statusOf(agents, "situation_analysis"),
            )}
            strokeWidth="1.5"
          />
          <line
            x1="170"
            y1="103"
            x2="170"
            y2="137"
            stroke={edgeColor(
              statusOf(agents, "situation_analysis"),
              commanderStatus,
            )}
            strokeWidth="1.5"
          />

          {/* ① + ② conditional fan-out into a parallel superstep */}
          {SPECIALISTS.map((role) => {
            const target = NODE_POSITIONS[role];
            const status = statusOf(agents, role);
            const stroke = edgeColor(commanderStatus, status);
            return (
              <path
                key={`out-${role}`}
                d={`M 170 167 C 170 205, ${target.x} 195, ${target.x} ${target.y - 15}`}
                fill="none"
                stroke={stroke}
                strokeWidth={isLive(status) ? 2 : 1.2}
                opacity={status === "skipped" ? 0.25 : 1}
                strokeDasharray={status === "skipped" ? "3 3" : undefined}
                className={isLive(status) ? "flow-line" : undefined}
              />
            );
          })}

          {/* ③ fan-in join */}
          {SPECIALISTS.map((role) => {
            const source = NODE_POSITIONS[role];
            const status = statusOf(agents, role);
            const stroke = edgeColor(status, allocationStatus);
            return (
              <path
                key={`in-${role}`}
                d={`M ${source.x} ${source.y + 15} C ${source.x} 300, 170 305, 170 325`}
                fill="none"
                stroke={stroke}
                strokeWidth="1.2"
                opacity={status === "skipped" ? 0.15 : 0.9}
              />
            );
          })}

          <line
            x1="170"
            y1="355"
            x2="170"
            y2="393"
            stroke={edgeColor(allocationStatus, reflectionStatus)}
            strokeWidth="1.5"
          />

          {/* ④ bounded reflection cycle */}
          <path
            d="M 185 408 C 250 408, 258 340, 185 340"
            fill="none"
            stroke={reflectionStatus === "completed" ? "#fb923c" : "#1b2438"}
            strokeWidth="1.5"
            strokeDasharray="3 2"
            markerEnd="url(#arrow)"
            className="text-[#fb923c]"
          />
          <text
            x="266"
            y="378"
            fontSize="7.5"
            fontFamily="var(--font-mono)"
            fill="#fb923c"
            opacity={reflectionStatus === "completed" ? 0.9 : 0.35}
          >
            revise
          </text>

          <line
            x1="170"
            y1="423"
            x2="170"
            y2="465"
            stroke={edgeColor(
              reflectionStatus,
              statusOf(agents, "communication"),
            )}
            strokeWidth="1.5"
          />

          {/* Superstep band */}
          <rect
            x="8"
            y="218"
            width="324"
            height="52"
            rx="6"
            fill="none"
            stroke="#1b2438"
            strokeDasharray="3 3"
          />
          <text
            x="14"
            y="214"
            fontSize="7.5"
            fontFamily="var(--font-mono)"
            fill="#5c6a85"
            letterSpacing="0.1em"
          >
            PARALLEL SUPERSTEP
          </text>

          {/* Nodes last, so they sit above every edge */}
          {node("intake", 13)}
          {node("situation_analysis")}
          {node("commander", 17)}
          {SPECIALISTS.map((role) => node(role, 14))}
          {node("allocation", 16)}
          {node("reflection")}
          {node("communication")}
        </svg>
      </div>

      <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 border-t border-edge px-1 pt-2">
        {SPECIALISTS.map((role) => {
          const status = statusOf(agents, role);
          return (
            <div key={role} className="flex items-center gap-1.5">
              <span
                className="size-1.5 shrink-0 rounded-full"
                style={{ background: STATUS_COLOR[status] }}
              />
              <span
                className={`truncate font-mono text-[9px] ${
                  status === "skipped" ? "text-ink-faint line-through" : "text-ink-dim"
                }`}
              >
                {AGENT_LABEL[role]}
              </span>
              {AGENT_SDG[role] && (
                <span className="ml-auto shrink-0 font-mono text-[8px] text-signal-deep">
                  {AGENT_SDG[role]}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
