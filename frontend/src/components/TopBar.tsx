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

function Pill({
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
      className="flex items-center gap-1.5 rounded border border-edge bg-panel px-2 py-1"
      title={detail}
    >
      <span
        className={`size-1.5 rounded-full ${ok ? "bg-emerald-400" : "bg-amber-400"}`}
      />
      <span className="font-mono text-[9px] tracking-wide text-ink-dim">
        {label}
      </span>
    </div>
  );
}

export function TopBar({ status, stats, running }: Props) {
  const cnnAccuracy = status?.vision.metadata?.cnn_val_accuracy as
    | number
    | undefined;

  return (
    <header className="flex shrink-0 items-center gap-4 border-b border-edge bg-panel px-4 py-2">
      <div className="flex items-baseline gap-2.5">
        <div className="flex items-center gap-2">
          <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
            <path
              d="M12 2 L21 6.5 V12 C21 17 17 21 12 22.5 C7 21 3 17 3 12 V6.5 Z"
              fill="none"
              stroke="var(--color-signal)"
              strokeWidth="1.6"
            />
            <circle cx="12" cy="12" r="2.6" fill="var(--color-signal)" />
          </svg>
          <h1 className="font-mono text-sm font-semibold tracking-[0.2em] text-ink">
            SENTINEL<span className="text-signal">AI</span>
          </h1>
        </div>
        <span className="hidden font-mono text-[9px] tracking-[0.12em] text-ink-faint lg:inline">
          PREDICT · COORDINATE · RESPOND · RECOVER
        </span>
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        {status && (
          <>
            <Pill
              label={status.deterministic_mode ? "RULE-BASED" : "LLM LIVE"}
              ok={!status.deterministic_mode}
              detail={status.llm.detail}
            />
            <Pill
              label={
                cnnAccuracy
                  ? `CNN ${Math.round(cnnAccuracy * 100)}%`
                  : "VISION"
              }
              ok={status.vision.available}
              detail={status.vision.detail}
            />
            <Pill
              label="RAG"
              ok={status.retrieval.available}
              detail={status.retrieval.detail}
            />
          </>
        )}

        <div className="mx-1 h-5 w-px bg-edge" />

        <div className="flex items-center gap-2.5 font-mono text-[9px] text-ink-faint">
          <span title="Agents engaged">
            AGT <span className="text-ink">{stats.activeAgents}</span>
          </span>
          <span title="Tool invocations">
            TOOL <span className="text-ink">{stats.toolCalls}</span>
          </span>
          <span title="Doctrine retrievals">
            RAG <span className="text-ink">{stats.retrievals}</span>
          </span>
          <span title="Reflection cycles">
            CRIT <span className="text-ink">{stats.critiques}</span>
          </span>
          {stats.fallbacks > 0 && (
            <span title="Tool calls served from fallback data" className="text-amber-400">
              FB {stats.fallbacks}
            </span>
          )}
        </div>

        <div className="ml-1 flex items-center gap-1.5 rounded border border-amber-500/30 bg-amber-500/5 px-2 py-1">
          <span className="font-mono text-[9px] tracking-wide text-amber-400">
            SIMULATED DATA
          </span>
        </div>

        {running && (
          <span className="flex items-center gap-1.5 rounded border border-signal-deep bg-signal/5 px-2 py-1">
            <span className="size-1.5 rounded-full bg-signal pulse-ring" />
            <span className="font-mono text-[9px] text-signal">LIVE</span>
          </span>
        )}
      </div>
    </header>
  );
}
