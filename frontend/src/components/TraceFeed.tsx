import { useEffect, useRef, useState } from "react";
import { AGENT_LABEL, EVENT_STYLE, clockTime } from "../lib/format";
import type { AgentTrace } from "../lib/types";

/**
 * The live operations feed.
 *
 * Auto-follows the tail while the operator is at the bottom, and stops
 * following the moment they scroll up to read something — the standard log
 * behaviour, and the difference between a usable feed and an unreadable one.
 */

interface Props {
  traces: AgentTrace[];
  running: boolean;
}

export function TraceFeed({ traces, running }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);
  const [filter, setFilter] = useState<"all" | "decisions">("all");

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

  const visible =
    filter === "all"
      ? traces
      : traces.filter((t) =>
          [
            "node_completed",
            "routing_decision",
            "critique",
            "revision",
            "retrieval",
            "run_started",
            "run_completed",
            "error",
          ].includes(t.event_type),
        );

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-center justify-between px-1">
        <h2 className="font-mono text-[10px] tracking-[0.18em] text-ink-dim">
          OPERATIONS FEED
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setFilter(filter === "all" ? "decisions" : "all")}
            className="rounded border border-edge px-1.5 py-0.5 font-mono text-[9px] text-ink-faint transition-colors hover:border-edge-bright hover:text-ink-dim"
          >
            {filter === "all" ? "ALL" : "DECISIONS"}
          </button>
          <span className="font-mono text-[9px] text-ink-faint">
            {visible.length}
          </span>
          {running && (
            <span className="size-1.5 rounded-full bg-signal pulse-ring" />
          )}
        </div>
      </div>

      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="min-h-0 flex-1 space-y-px overflow-y-auto pr-1"
      >
        {visible.length === 0 && (
          <p className="px-2 py-6 text-center font-mono text-[10px] text-ink-faint">
            Awaiting incident…
          </p>
        )}

        {visible.map((trace) => {
          const style = EVENT_STYLE[trace.event_type];
          const fallback = trace.tool_invocation?.used_fallback;

          return (
            <div
              key={trace.event_id}
              className="trace-in group rounded px-1.5 py-1 transition-colors hover:bg-panel-raised"
            >
              <div className="flex items-start gap-1.5">
                <span
                  className="mt-px shrink-0 font-mono text-[10px] leading-4"
                  style={{ color: style.color }}
                  aria-hidden
                >
                  {style.glyph}
                </span>

                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-1.5">
                    <span className="truncate font-mono text-[9px] text-ink-faint">
                      {AGENT_LABEL[trace.agent] ?? trace.agent}
                    </span>
                    <span className="ml-auto shrink-0 font-mono text-[8px] text-ink-faint opacity-0 transition-opacity group-hover:opacity-100">
                      {clockTime(trace.timestamp)}
                    </span>
                  </div>

                  <p className="text-[11px] leading-snug text-ink">
                    {trace.title}
                  </p>

                  {trace.detail && (
                    <p className="mt-0.5 line-clamp-2 text-[10px] leading-snug text-ink-dim">
                      {trace.detail}
                    </p>
                  )}

                  <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                    {typeof trace.confidence === "number" && (
                      <span className="font-mono text-[8px] text-signal-deep">
                        conf {Math.round(trace.confidence * 100)}%
                      </span>
                    )}
                    {typeof trace.latency_ms === "number" &&
                      trace.latency_ms > 0 && (
                        <span className="font-mono text-[8px] text-ink-faint">
                          {trace.latency_ms}ms
                        </span>
                      )}
                    {fallback && (
                      <span className="rounded bg-amber-500/10 px-1 font-mono text-[8px] text-amber-400">
                        FALLBACK
                      </span>
                    )}
                    {trace.status === "degraded" && (
                      <span className="rounded bg-amber-500/10 px-1 font-mono text-[8px] text-amber-400">
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
          className="mt-1 rounded border border-edge bg-panel-raised py-1 font-mono text-[9px] text-signal transition-colors hover:border-signal-deep"
        >
          ↓ RESUME FOLLOW
        </button>
      )}
    </div>
  );
}
