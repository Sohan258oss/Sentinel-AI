import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Scenario } from "../lib/types";

interface Props {
  onLaunch: (key: string) => void;
  onOpenCustomModal: () => void;
  running: boolean;
  activeKey: string | null;
}

export function ScenarioLauncher({
  onLaunch,
  onOpenCustomModal,
  running,
  activeKey,
}: Props) {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<string>("ALL");

  useEffect(() => {
    api.scenarios().then(setScenarios).catch(() => setScenarios([]));
  }, []);

  const filteredScenarios = scenarios.filter((s) => {
    if (selectedRegion === "ALL") return true;
    return s.title.toLowerCase().includes(selectedRegion.toLowerCase());
  });

  return (
    <div className="flex flex-col gap-2.5">
      {/* Header with Title and Custom Incident CTA */}
      <div className="flex items-center justify-between px-0.5">
        <h2 className="font-mono text-[10.5px] font-bold tracking-[0.16em] text-ink-dim uppercase flex items-center gap-1.5">
          <span className="size-1.5 rounded-full bg-signal" />
          INCIDENTS & SCENARIOS
        </h2>
        <button
          onClick={onOpenCustomModal}
          disabled={running}
          className="rounded border border-signal-deep bg-signal/15 px-2 py-1 font-mono text-[9.5px] font-semibold text-signal hover:bg-signal/25 disabled:opacity-50 transition-all shadow-sm flex items-center gap-1"
        >
          <span>+</span> Custom
        </button>
      </div>

      {/* Region Filter Chips */}
      <div className="flex items-center gap-1 overflow-x-auto pb-1 no-scrollbar">
        {[
          { label: "All India", key: "ALL" },
          { label: "Kerala", key: "Kerala" },
          { label: "Assam", key: "Assam" },
          { label: "Uttarakhand", key: "Uttarakhand" },
          { label: "Odisha", key: "Odisha" },
          { label: "Delhi", key: "Delhi" },
        ].map((r) => (
          <button
            key={r.key}
            onClick={() => setSelectedRegion(r.key)}
            className={`shrink-0 rounded-full px-2.5 py-0.5 font-mono text-[9.5px] transition-all ${
              selectedRegion === r.key
                ? "bg-signal-deep text-void font-bold shadow-sm"
                : "bg-abyss/80 text-ink-faint border border-edge/40 hover:text-ink hover:border-edge"
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>

      {/* Scenario List */}
      <div className="flex flex-col gap-1.5 max-h-[310px] overflow-y-auto pr-1">
        {filteredScenarios.map((scenario) => {
          const isActive = activeKey === scenario.key;
          return (
            <div
              key={scenario.key}
              className={`rounded-lg border transition-all ${
                isActive
                  ? "border-signal-deep bg-signal/10 shadow-[0_0_12px_rgba(34,211,238,0.15)]"
                  : "border-edge/70 bg-panel/70 hover:border-edge-bright hover:bg-panel"
              }`}
            >
              <button
                disabled={running}
                onClick={() => onLaunch(scenario.key)}
                onMouseEnter={() => setExpanded(scenario.key)}
                onMouseLeave={() => setExpanded(null)}
                className="w-full p-2 text-left disabled:cursor-not-allowed disabled:opacity-50"
              >
                <div className="flex items-center justify-between gap-1.5">
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className={`size-2 shrink-0 rounded-full ${
                        isActive && running
                          ? "bg-signal pulse-ring"
                          : isActive
                            ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]"
                            : "bg-edge-bright"
                      }`}
                    />
                    <span className="truncate text-xs font-semibold text-ink">
                      {scenario.title}
                    </span>
                  </div>
                  {isActive && running && (
                    <span className="shrink-0 font-mono text-[8.5px] font-bold text-signal bg-signal/20 px-1.5 py-0.5 rounded">
                      ACTIVE
                    </span>
                  )}
                </div>

                <p className="mt-1 text-[10px] leading-relaxed text-ink-dim line-clamp-2">
                  {expanded === scenario.key
                    ? scenario.demonstrates
                    : scenario.description}
                </p>
              </button>
            </div>
          );
        })}

        {filteredScenarios.length === 0 && scenarios.length > 0 && (
          <p className="px-2 py-4 text-center font-mono text-[10px] text-ink-faint">
            No scenarios found for this region filter
          </p>
        )}

        {scenarios.length === 0 && (
          <div className="px-2 py-4 text-center font-mono text-[10px] text-ink-faint">
            <span className="animate-pulse text-amber-400">Loading scenarios…</span>
          </div>
        )}
      </div>
    </div>
  );
}

