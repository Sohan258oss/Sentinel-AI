import { useEffect, useState } from "react";
import type { SystemStatus } from "../lib/types";

interface Props {
  status: SystemStatus | null;
  stats: {
    toolCalls: number;
    retrievals: number;
    critiques: number;
    fallbacks: number;
    activeAgents: number;
  };
  running: boolean;
}

function StatusBadge({
  label,
  ok,
  detail,
}: {
  label: string;
  ok: boolean;
  detail: string;
}) {
  return (
    <div
      className="flex items-center gap-1.5 rounded-full border border-edge bg-abyss/80 px-2.5 py-0.5 transition-colors hover:border-edge-bright"
      title={detail}
    >
      <span
        className={`size-1.5 rounded-full ${
          ok ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.6)]" : "bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.6)]"
        }`}
      />
      <span className="font-mono text-[10px] font-medium tracking-wide text-ink-dim">
        {label}
      </span>
    </div>
  );
}

export function TopBar({ status, stats, running }: Props) {
  const [timeStr, setTimeStr] = useState<string>("");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTimeStr(now.toLocaleTimeString("en-US", { hour12: false }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const cnnAccuracy = status?.vision.metadata?.cnn_val_accuracy as
    | number
    | undefined;

  return (
    <header className="flex h-[52px] shrink-0 items-center justify-between border-b border-edge bg-panel/90 px-4 backdrop-blur-md">
      {/* Brand & Subtitle */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="relative flex items-center justify-center">
            <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden>
              <path
                d="M12 2 L21 6.5 V12 C21 17 17 21 12 22.5 C7 21 3 17 3 12 V6.5 Z"
                fill="rgba(34, 211, 238, 0.1)"
                stroke="var(--color-signal)"
                strokeWidth="1.8"
              />
              <circle cx="12" cy="12" r="3" fill="var(--color-signal)" />
            </svg>
            <span className="absolute size-3 rounded-full bg-signal/20 animate-ping" />
          </div>
          <h1 className="font-mono text-base font-bold tracking-[0.22em] text-ink">
            SENTINEL<span className="text-signal font-extrabold">AI</span>
          </h1>
        </div>

        <span className="hidden font-mono text-[10px] tracking-[0.15em] text-ink-faint border-l border-edge pl-3 lg:inline">
          CRISIS COMMAND & AUTONOMOUS DISPATCH CENTER
        </span>
      </div>

      {/* Right-side System Telemetry & Status */}
      <div className="flex items-center gap-2.5">
        {status && (
          <div className="hidden sm:flex items-center gap-1.5">
            <StatusBadge
              label={status.deterministic_mode ? "RULE-BASED" : "LLM LIVE"}
              ok={!status.deterministic_mode}
              detail={status.llm.detail}
            />
            <StatusBadge
              label={
                cnnAccuracy
                  ? `VISION ${Math.round(cnnAccuracy * 100)}%`
                  : "VISION READY"
              }
              ok={status.vision.available}
              detail={status.vision.detail}
            />
            <StatusBadge
              label="RAG DOCTRINE"
              ok={status.retrieval.available}
              detail={status.retrieval.detail}
            />
          </div>
        )}

        <div className="hidden md:block h-4 w-px bg-edge mx-1" />

        {/* Telemetry Counter */}
        <div className="flex items-center gap-3 rounded-md border border-edge/60 bg-abyss/60 px-3 py-1 font-mono text-[10px] text-ink-faint">
          <span title="Agents engaged" className="flex items-center gap-1">
            AGENTS <span className="font-bold text-signal">{stats.activeAgents}</span>
          </span>
          <span title="Tool invocations" className="flex items-center gap-1">
            TOOLS <span className="font-bold text-ink">{stats.toolCalls}</span>
          </span>
          <span title="Doctrine retrievals" className="flex items-center gap-1">
            RAG <span className="font-bold text-ink">{stats.retrievals}</span>
          </span>
          <span title="Reflection cycles" className="flex items-center gap-1">
            AUDITS <span className="font-bold text-amber-400">{stats.critiques}</span>
          </span>
          {stats.fallbacks > 0 && (
            <span title="Tool calls served from fallback data" className="text-amber-400 font-bold">
              FB {stats.fallbacks}
            </span>
          )}
        </div>

        {/* Clock & Live Indicator */}
        <div className="flex items-center gap-2">
          {running ? (
            <div className="flex items-center gap-1.5 rounded-full border border-signal/40 bg-signal/10 px-2.5 py-0.5">
              <span className="size-2 rounded-full bg-signal pulse-ring" />
              <span className="font-mono text-[10px] font-bold text-signal tracking-wide">
                DISPATCH LIVE
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 rounded-full border border-edge bg-abyss px-2.5 py-0.5">
              <span className="size-1.5 rounded-full bg-emerald-400" />
              <span className="font-mono text-[10px] font-medium text-ink-faint">
                STANDBY
              </span>
            </div>
          )}

          {timeStr && (
            <div className="hidden xl:block rounded border border-edge/40 bg-panel px-2 py-0.5 font-mono text-[11px] font-semibold text-ink-dim tracking-wider">
              {timeStr}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

