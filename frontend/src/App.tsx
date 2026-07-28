import { useEffect, useState } from "react";
import { AgentGraph } from "./components/AgentGraph";
import { OperationalPanels } from "./components/OperationalPanels";
import { ScenarioLauncher } from "./components/ScenarioLauncher";
import { TacticalMap } from "./components/TacticalMap";
import { TopBar } from "./components/TopBar";
import { TraceFeed } from "./components/TraceFeed";
import { useIncidentRun } from "./hooks/useIncidentRun";
import { api } from "./lib/api";
import { relativeDuration } from "./lib/format";
import type { SystemStatus } from "./lib/types";

export default function App() {
  const run = useIncidentRun();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [activeScenario, setActiveScenario] = useState<string | null>(null);

  useEffect(() => {
    api.systemStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const launch = (key: string) => {
    setActiveScenario(key);
    void run.start(key);
  };

  const picture = run.picture;
  const report = picture?.report;

  return (
    <div className="flex h-full flex-col bg-void">
      <TopBar status={status} stats={run.stats} running={run.running} />

      {status?.deterministic_mode && (
        <div className="shrink-0 border-b border-amber-500/20 bg-amber-500/5 px-4 py-1">
          <p className="font-mono text-[9.5px] text-amber-400/90">
            DETERMINISTIC MODE — no language model configured. Agents are running
            rule-based domain logic and their output is marked DEGRADED. Set
            SENTINEL_GOOGLE_API_KEY to enable model reasoning.
          </p>
        </div>
      )}

      {run.error && (
        <div className="shrink-0 border-b border-red-500/20 bg-red-500/5 px-4 py-1">
          <p className="font-mono text-[9.5px] text-red-400">{run.error}</p>
        </div>
      )}

      <main className="grid min-h-0 flex-1 grid-cols-[236px_1fr_312px] gap-2 p-2">
        {/* Left rail: control + graph */}
        <div className="flex min-h-0 flex-col gap-2">
          <div className="shrink-0 rounded border border-edge bg-panel p-2">
            <ScenarioLauncher
              onLaunch={launch}
              running={run.running}
              activeKey={activeScenario}
            />
          </div>
          <div className="min-h-0 flex-1 rounded border border-edge bg-panel p-2">
            <AgentGraph agents={run.agents} />
          </div>
        </div>

        {/* Centre: situation display + operational picture.
            min-w-0 is load-bearing: without it the long incident description
            sets the track's min-content width and pushes the right rail off
            screen. */}
        <div className="flex min-h-0 min-w-0 flex-col gap-2">
          <div className="shrink-0 rounded border border-edge bg-panel px-3 py-1.5">
            <div className="flex items-center gap-3">
              <div className="min-w-0">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[10px] text-signal">
                    {picture?.incident_id ?? run.incidentId ?? "NO ACTIVE INCIDENT"}
                  </span>
                  {report && (
                    <span className="truncate font-mono text-[10px] text-ink-dim">
                      {report.location.name}
                      {report.location.district
                        ? `, ${report.location.district}`
                        : ""}
                    </span>
                  )}
                </div>
                {report && (
                  <p className="line-clamp-1 text-[10.5px] text-ink-faint">
                    {report.description}
                  </p>
                )}
              </div>

              {picture && (
                <div className="ml-auto flex shrink-0 items-center gap-3 font-mono text-[9px] text-ink-faint">
                  <span>
                    STATUS <span className="text-ink">{picture.status}</span>
                  </span>
                  <span>
                    RUNTIME{" "}
                    <span className="text-ink">
                      {relativeDuration(
                        picture.created_at,
                        picture.completed_at,
                      )}
                    </span>
                  </span>
                </div>
              )}
            </div>
          </div>

          <div className="min-h-0 flex-[3]">
            <TacticalMap
              incidentPoint={report?.location.point ?? null}
              incidentName={report?.location.name}
              assessment={picture?.assessment ?? null}
              allocationPlan={picture?.allocation_plan ?? null}
            />
          </div>

          <div className="min-h-0 flex-[4] rounded border border-edge bg-panel">
            <OperationalPanels picture={picture} />
          </div>
        </div>

        {/* Right rail: live feed */}
        <div className="min-h-0 rounded border border-edge bg-panel p-2">
          <TraceFeed traces={run.traces} running={run.running} />
        </div>
      </main>
    </div>
  );
}
