/**
 * App — World Monitor–style full-bleed map layout.
 *
 * The map fills the entire viewport as the primary canvas. All panels
 * (scenarios, trace feed, operational data) are glassmorphic floating overlays
 * that can be collapsed to give the map maximum space. News articles surface
 * as a bottom ticker and a right-side floating panel — the same pattern used
 * by World Monitor.
 */
import { useEffect, useMemo, useState } from "react";
import { AgentGraph } from "./components/AgentGraph";
import { AgentInspectorModal } from "./components/AgentInspectorModal";
import { CustomIncidentModal } from "./components/CustomIncidentModal";
import { NewsPanel } from "./components/NewsPanel";
import { NewsTicker } from "./components/NewsTicker";
import { OperationalPanels } from "./components/OperationalPanels";
import { ScenarioLauncher } from "./components/ScenarioLauncher";
import { TacticalMap } from "./components/TacticalMap";
import { TopBar } from "./components/TopBar";
import { TraceFeed } from "./components/TraceFeed";
import { useIncidentRun } from "./hooks/useIncidentRun";
import { api } from "./lib/api";
import { relativeDuration, SEVERITY_COLOR } from "./lib/format";
import type { AgentRole, NewsArticle, SystemStatus } from "./lib/types";

export default function App() {
  const run = useIncidentRun();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [activeScenario, setActiveScenario] = useState<string | null>(null);
  const [isCustomModalOpen, setIsCustomModalOpen] = useState(false);

  // Agent inspection & map highlighting states
  const [selectedAgent, setSelectedAgent] = useState<AgentRole | null>(null);
  const [hoveredAgent, setHoveredAgent] = useState<AgentRole | null>(null);
  const [inspectorMinimized, setInspectorMinimized] = useState(false);

  // Drawer visibility states
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [opsOpen, setOpsOpen] = useState(false);
  const [newsPanelOpen, setNewsPanelOpen] = useState(false);

  useEffect(() => {
    api.systemStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const launch = (key: string) => {
    setActiveScenario(key);
    // Auto-open news panel when a run starts
    setNewsPanelOpen(true);
    void run.start(key);
  };

  const handleCustomSubmit = (payload: Record<string, unknown>) => {
    setActiveScenario(null);
    setNewsPanelOpen(true);
    void run.startCustom(payload);
  };

  const picture = run.picture;
  const report = picture?.report;

  // Extract news articles from the trace stream's tool_result events
  const { newsArticles, informationGap } = useMemo(() => {
    const newsTrace = run.traces.find(
      (t) =>
        t.event_type === "tool_result" &&
        t.tool_invocation?.tool_name === "search_news",
    );
    if (!newsTrace) return { newsArticles: [] as NewsArticle[], informationGap: null };

    const result = newsTrace.payload?.result as Record<string, unknown> | undefined;
    if (!result) return { newsArticles: [] as NewsArticle[], informationGap: null };

    const articles = (result.articles as NewsArticle[] | undefined) ?? [];
    const gap = result.feed_available === false
      ? (result.information_gap as string | null) ?? null
      : null;

    return { newsArticles: articles, informationGap: gap };
  }, [run.traces]);

  const severity = picture?.assessment?.severity ?? "informational";
  const severityColor = SEVERITY_COLOR[severity];
  const hazardType = picture?.assessment?.hazard_type;

  // Auto-open news panel when articles arrive
  useEffect(() => {
    if (newsArticles.length > 0) setNewsPanelOpen(true);
  }, [newsArticles.length]);

  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-void">
      {/* ── Top bar (fixed height, above map) ─────────────────────────── */}
      <div className="relative z-40 shrink-0">
        <TopBar status={status} stats={run.stats} running={run.running} />

        {status?.deterministic_mode && (
          <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-1.5 shadow-inner">
            <p className="font-mono text-[10px] font-semibold text-amber-300 flex items-center gap-2">
              <span className="size-2 rounded-full bg-amber-400 animate-pulse" />
              DETERMINISTIC MODE — no language model configured. Agents run rule-based domain logic and output is marked DEGRADED. Set SENTINEL_GOOGLE_API_KEY to enable LLM reasoning.
            </p>
          </div>
        )}

        {run.error && (
          <div className="border-b border-red-500/30 bg-red-500/10 px-4 py-1.5">
            <p className="font-mono text-[10px] font-bold text-red-400 flex items-center gap-2">
              <span>✕</span> {run.error}
            </p>
          </div>
        )}
      </div>

      {/* ── Full-bleed map canvas area ─────────────────────────────────── */}
      <div className="relative min-h-0 flex-1 overflow-hidden">
        {/* Map fills everything */}
        <TacticalMap
          mapboxToken={status?.mapbox_token}
          incidentPoint={report?.location.point ?? null}
          incidentName={report?.location.name}
          assessment={picture?.assessment ?? null}
          allocationPlan={picture?.allocation_plan ?? null}
          activeAgentRole={selectedAgent || hoveredAgent}
        />

        {/* ── Incident HUD chip — top-center ── */}
        {(run.incidentId || picture) && (
          <div className="absolute left-1/2 top-2.5 z-20 -translate-x-1/2 pointer-events-auto">
            <div
              className="flex items-center gap-3 rounded-full border px-4 py-1 font-mono text-[10.5px] backdrop-blur-md shadow-2xl transition-all"
              style={{
                background: "rgba(8, 13, 26, 0.92)",
                borderColor: `${severityColor}60`,
                boxShadow: `0 0 25px ${severityColor}25, 0 8px 30px rgba(0,0,0,0.6)`,
              }}
            >
              <span
                className={`size-2 rounded-full ${run.running ? "pulse-ring" : ""}`}
                style={{ background: severityColor }}
              />
              <span className="font-extrabold tracking-wide" style={{ color: severityColor }}>
                {picture?.incident_id ?? run.incidentId}
              </span>
              {report && (
                <span className="text-ink font-semibold">
                  {report.location.name}
                  {report.location.state ? `, ${report.location.state}` : ""}
                </span>
              )}
              {picture && (
                <>
                  <span className="text-edge-bright">·</span>
                  <span className="text-ink-dim uppercase font-bold text-[9.5px]">
                    {picture.status}
                  </span>
                  <span className="text-edge-bright">·</span>
                  <span className="text-ink-faint">
                    {relativeDuration(picture.created_at, picture.completed_at)}
                  </span>
                </>
              )}
            </div>
          </div>
        )}

        {/* ── Floating OSINT News Panel — anchored gracefully ── */}
        <div
          className={`absolute top-3 z-30 transition-all duration-300 pointer-events-none ${
            rightOpen ? "right-[328px]" : "right-3"
          }`}
        >
          <div className="pointer-events-auto">
            <NewsPanel
              articles={newsArticles}
              isOpen={newsPanelOpen}
              onClose={() => setNewsPanelOpen(false)}
              incidentName={report?.location.name}
              hazardType={hazardType}
              severityColor={severityColor}
              informationGap={informationGap}
            />
          </div>
        </div>

        {/* ── Ops panel toggle — bottom-center ── */}
        <div className="absolute bottom-10 left-1/2 z-20 -translate-x-1/2 pointer-events-auto">
          <button
            onClick={() => setOpsOpen((v) => !v)}
            className="flex items-center gap-2 rounded-full border border-edge-bright bg-panel/90 px-4 py-1.5 font-mono text-[10px] font-bold text-ink-dim backdrop-blur-md shadow-xl hover:border-signal hover:text-signal transition-all"
          >
            <span>{opsOpen ? "▼" : "▲"}</span>
            {opsOpen ? "Hide Operational Analysis" : "Show Operational Analysis"}
            {picture && (
              <span className="rounded-full bg-signal-deep/30 px-1.5 text-[9px] text-signal font-bold">
                READY
              </span>
            )}
          </button>
        </div>

        {/* ── Left Drawer Collapsed Toggle ── */}
        {!leftOpen && (
          <button
            onClick={() => setLeftOpen(true)}
            className="absolute left-3 top-3 z-30 flex items-center gap-1.5 rounded-lg border border-edge-bright bg-panel/95 px-3 py-1.5 font-mono text-[10px] font-bold text-ink-dim backdrop-blur-md shadow-xl hover:border-signal hover:text-signal pointer-events-auto transition-all"
          >
            <span>▶</span> SCENARIOS
          </button>
        )}

        {/* ── Left drawer — Scenarios + Agent graph ─────────────────────── */}
        {leftOpen && (
          <div className="absolute left-0 top-0 bottom-0 z-30 w-[272px] flex flex-col gap-2 p-2.5 pointer-events-auto">
            <div className="relative shrink-0 rounded-xl border border-edge bg-panel/95 p-2.5 backdrop-blur-md shadow-2xl">
              {/* Internal Collapse Toggle */}
              <button
                onClick={() => setLeftOpen(false)}
                title="Collapse Left Drawer"
                className="absolute right-2 top-2 rounded p-1 font-mono text-[10px] text-ink-faint hover:bg-edge hover:text-ink transition-colors"
              >
                ◀
              </button>
              <ScenarioLauncher
                onLaunch={launch}
                onOpenCustomModal={() => setIsCustomModalOpen(true)}
                running={run.running}
                activeKey={activeScenario}
              />
            </div>
            <div className="min-h-0 flex-1 rounded-xl border border-edge bg-panel/95 p-2.5 backdrop-blur-md shadow-2xl">
              <AgentGraph
                agents={run.agents}
                onSelect={(role) => setSelectedAgent(role)}
                onHover={(role) => setHoveredAgent(role)}
                selected={selectedAgent}
              />
            </div>
          </div>
        )}

        {/* ── Right Drawer Collapsed Toggle ── */}
        {!rightOpen && (
          <button
            onClick={() => setRightOpen(true)}
            className="absolute right-3 top-3 z-30 flex items-center gap-1.5 rounded-lg border border-edge-bright bg-panel/95 px-3 py-1.5 font-mono text-[10px] font-bold text-ink-dim backdrop-blur-md shadow-xl hover:border-signal hover:text-signal pointer-events-auto transition-all"
          >
            <span>📡 OSINT & FEED</span> ◀
          </button>
        )}

        {/* ── Right drawer — Operations Feed & OSINT ───────────────────── */}
        {rightOpen && (
          <div className="absolute right-0 top-0 bottom-0 z-30 w-[316px] p-2.5 pointer-events-auto">
            <div className="relative h-full rounded-xl border border-edge bg-panel/95 p-2.5 backdrop-blur-md shadow-2xl">
              {/* Internal Collapse Toggle */}
              <button
                onClick={() => setRightOpen(false)}
                title="Collapse Right Drawer"
                className="absolute right-2 top-2 rounded p-1 font-mono text-[10px] text-ink-faint hover:bg-edge hover:text-ink transition-colors z-10"
              >
                ▶
              </button>
              <TraceFeed
                traces={run.traces}
                running={run.running}
                newsCount={newsArticles.length}
                onToggleNews={() => setNewsPanelOpen((v) => !v)}
                isNewsOpen={newsPanelOpen}
              />
            </div>
          </div>
        )}

        {/* ── Operational Analysis panel — slides up from the bottom ── */}
        {opsOpen && picture && (
          <div
            className="absolute bottom-0 left-0 right-0 z-20 border-t border-edge bg-panel/95 backdrop-blur-lg shadow-2xl"
            style={{ height: "350px" }}
          >
            <OperationalPanels picture={picture} />
          </div>
        )}
      </div>

      {/* ── News Ticker — always at the very bottom ── */}
      <div className="shrink-0 z-40">
        <NewsTicker
          articles={newsArticles}
          running={run.running}
          severityColor={severityColor}
        />
      </div>

      {/* ── Custom Incident Modal ─────────────────────────────────────── */}
      <CustomIncidentModal
        isOpen={isCustomModalOpen}
        onClose={() => setIsCustomModalOpen(false)}
        onSubmit={handleCustomSubmit}
        disabled={run.running}
      />

      {/* ── Agent Telemetry Inspector Modal ────────────────────────── */}
      <AgentInspectorModal
        role={selectedAgent}
        agentState={selectedAgent ? run.agents[selectedAgent] ?? null : null}
        traces={run.traces}
        onClose={() => { setSelectedAgent(null); setInspectorMinimized(false); }}
        minimized={inspectorMinimized}
        onMinimize={() => setInspectorMinimized(true)}
        onRestore={() => setInspectorMinimized(false)}
      />
    </div>
  );
}


