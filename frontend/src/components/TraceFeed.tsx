import { useEffect, useRef, useState } from "react";
import { AGENT_LABEL, EVENT_STYLE, clockTime } from "../lib/format";
import type { AgentTrace } from "../lib/types";

interface Props {
  traces: AgentTrace[];
  running: boolean;
  newsCount?: number;
  onToggleNews?: () => void;
  isNewsOpen?: boolean;
}

type FilterMode = "all" | "decisions" | "tools" | "errors";

export function TraceFeed({ traces, running, newsCount = 0, onToggleNews, isNewsOpen }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);
  const [filter, setFilter] = useState<FilterMode>("all");

  useEffect(() => {
    if (!follow || !containerRef.current) return;
    containerRef.current.scrollTop = containerRef.current.scrollHeight;
  }, [traces, follow]);

  const handleScroll = () => {
    const element = containerRef.current;
    if (!element) return;
    const atBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight < 40;
    setFollow(atBottom);
  };

  const visible = traces.filter((t) => {
    if (filter === "all") return true;
    if (filter === "decisions") {
      return [
        "node_completed",
        "routing_decision",
        "critique",
        "revision",
        "retrieval",
        "run_started",
        "run_completed",
        "error",
      ].includes(t.event_type);
    }
    if (filter === "tools") {
      return ["tool_call", "tool_result", "retrieval"].includes(t.event_type);
    }
    if (filter === "errors") {
      return ["node_failed", "error"].includes(t.event_type) || t.status === "degraded";
    }
    return true;
  });

  return (
    <div className="flex h-full flex-col">
      {/* Header & Filter Toolbar */}
      <div className="mb-2 flex flex-col gap-1.5 px-0.5 pb-1 border-b border-edge/60">
        <div className="flex items-center justify-between">
          <h2 className="font-mono text-[10.5px] font-bold tracking-[0.16em] text-ink-dim uppercase flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-signal" />
            OPERATIONS FEED
          </h2>
          <div className="flex items-center gap-1.5">
            {onToggleNews && (
              <button
                onClick={onToggleNews}
                className={`flex items-center gap-1.5 rounded px-2 py-0.5 font-mono text-[9px] font-bold transition-all ${
                  isNewsOpen
                    ? "bg-signal text-void shadow-sm"
                    : "bg-abyss text-signal border border-signal/40 hover:bg-signal/15"
                }`}
                title="Toggle OSINT News Panel"
              >
                <span>📡 OSINT</span>
                {newsCount > 0 && (
                  <span className="rounded-full bg-signal-deep px-1 text-[8.5px] text-white">
                    {newsCount}
                  </span>
                )}
              </button>
            )}
            <span className="font-mono text-[9.5px] font-semibold text-ink-dim bg-abyss px-1.5 py-0.5 rounded border border-edge/40">
              {visible.length}
            </span>
            {running && (
              <span className="size-2 rounded-full bg-signal pulse-ring" />
            )}
          </div>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1">
          {(["all", "decisions", "tools", "errors"] as FilterMode[]).map((mode) => (
            <button
              key={mode}
              onClick={() => setFilter(mode)}
              className={`rounded px-2 py-0.5 font-mono text-[9px] font-semibold uppercase transition-all ${
                filter === mode
                  ? "bg-signal-deep text-void shadow-sm"
                  : "bg-abyss/80 text-ink-faint border border-edge/40 hover:text-ink"
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {/* Feed Container */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1"
      >
        {visible.length === 0 && (
          <div className="px-2 py-10 text-center font-mono text-[10.5px] text-ink-faint">
            Awaiting incident dispatch traces…
          </div>
        )}

        {visible.map((trace) => {
          const style = EVENT_STYLE[trace.event_type];
          const fallback = trace.tool_invocation?.used_fallback;

          return (
            <div
              key={trace.event_id}
              className="trace-in group rounded-md border border-edge/40 bg-panel/60 p-2 transition-all hover:border-edge-bright hover:bg-panel-raised"
            >
              <div className="flex items-start gap-2">
                <span
                  className="mt-0.5 shrink-0 rounded bg-abyss px-1.5 py-0.5 font-mono text-[10px] font-bold"
                  style={{ color: style.color, border: `1px solid ${style.color}30` }}
                  aria-hidden
                >
                  {style.glyph}
                </span>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-1 mb-0.5">
                    <span className="truncate font-mono text-[9.5px] font-bold text-signal">
                      {AGENT_LABEL[trace.agent] ?? trace.agent}
                    </span>
                    <span className="shrink-0 font-mono text-[8.5px] text-ink-faint">
                      {clockTime(trace.timestamp)}
                    </span>
                  </div>

                  <p className="text-[11.5px] font-medium leading-snug text-ink">
                    {trace.title}
                  </p>

                  {trace.detail && (
                    <p className="mt-1 line-clamp-3 text-[10.5px] leading-relaxed text-ink-dim">
                      {trace.detail}
                    </p>
                  )}

                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {typeof trace.confidence === "number" && (
                      <span className="font-mono text-[8.5px] font-bold text-emerald-400 bg-emerald-500/10 px-1.5 py-0.2 rounded border border-emerald-500/20">
                        conf {Math.round(trace.confidence * 100)}%
                      </span>
                    )}
                    {typeof trace.latency_ms === "number" &&
                      trace.latency_ms > 0 && (
                        <span className="font-mono text-[8.5px] text-ink-faint">
                          {trace.latency_ms}ms
                        </span>
                      )}
                    {fallback && (
                      <span className="rounded bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.2 font-mono text-[8.5px] font-bold text-amber-400">
                        FALLBACK
                      </span>
                    )}
                    {trace.status === "degraded" && (
                      <span className="rounded bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.2 font-mono text-[8.5px] font-bold text-amber-400">
                        DEGRADED
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {!follow && (
        <button
          onClick={() => setFollow(true)}
          className="mt-1.5 rounded-md border border-signal-deep/60 bg-signal/15 py-1 font-mono text-[10px] font-semibold text-signal transition-all hover:bg-signal/25 shadow-md"
        >
          ↓ RESUME AUTO-SCROLL
        </button>
      )}
    </div>
  );
}


