import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Scenario } from "../lib/types";

interface Props {
  onLaunch: (key: string) => void;
  running: boolean;
  activeKey: string | null;
}

export function ScenarioLauncher({ onLaunch, running, activeKey }: Props) {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    api.scenarios().then(setScenarios).catch(() => setScenarios([]));
  }, []);

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between px-1">
        <h2 className="font-mono text-[10px] tracking-[0.18em] text-ink-dim">
          INCIDENT SIMULATOR
        </h2>
      </div>

      {scenarios.map((scenario) => {
        const isActive = activeKey === scenario.key;
        return (
          <div
            key={scenario.key}
            className={`rounded border transition-colors ${
              isActive
                ? "border-signal-deep bg-signal/5"
                : "border-edge bg-panel hover:border-edge-bright"
            }`}
          >
            <button
              disabled={running}
              onClick={() => onLaunch(scenario.key)}
              onMouseEnter={() => setExpanded(scenario.key)}
              onMouseLeave={() => setExpanded(null)}
              className="w-full px-2 py-1.5 text-left disabled:cursor-not-allowed disabled:opacity-50"
            >
              <div className="flex items-center gap-1.5">
                <span
                  className={`size-1.5 shrink-0 rounded-full ${
                    isActive && running
                      ? "bg-signal pulse-ring"
                      : isActive
                        ? "bg-emerald-400"
                        : "bg-edge-bright"
                  }`}
                />
                <span className="truncate text-[11px] font-medium text-ink">
                  {scenario.title}
                </span>
              </div>
              <p className="mt-0.5 pl-3 text-[9.5px] leading-snug text-ink-faint">
                {expanded === scenario.key
                  ? scenario.demonstrates
                  : scenario.description}
              </p>
            </button>
          </div>
        );
      })}

      {scenarios.length === 0 && (
        <p className="px-2 py-3 text-center font-mono text-[10px] text-ink-faint">
          Backend unreachable
        </p>
      )}
    </div>
  );
}
