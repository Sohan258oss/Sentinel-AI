import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { AgentTrace, SystemStatus } from "../lib/types";
import { AGENT_LABEL } from "../lib/format";

interface Props {
  currentLocation: { state: string; district: string; hazard: string };
  onLocationChange: (state: string, district: string, hazard: string) => void;
  traces: AgentTrace[];
  agents: Record<string, any>;
  running: boolean;
  status: SystemStatus | null;
  picture: any;
}

interface LocationState {
  code: string;
  name: string;
  type: string;
  districts: Array<{
    name: string;
    hq: string;
    lat: number;
    lon: number;
    pop: number;
    primary_hazard: string;
    helpline: string;
  }>;
}

const HAZARDS = [
  { value: "flood", label: "🌊 Flood" },
  { value: "cyclone", label: "🌀 Cyclone" },
  { value: "earthquake", label: "🏚️ Earthquake" },
  { value: "landslide", label: "⛰️ Landslide" },
  { value: "heatwave", label: "☀️ Heatwave" },
  { value: "wildfire", label: "🔥 Wildfire" },
];

export function MorePage({
  currentLocation,
  onLocationChange,
  traces,
  agents,
  running: _running,
  status,
  picture: _picture,
}: Props) {
  const [locations, setLocations] = useState<LocationState[]>([]);
  const [selectedState, setSelectedState] = useState(currentLocation.state);
  const [selectedDistrict, setSelectedDistrict] = useState(currentLocation.district);
  const [selectedHazard, setSelectedHazard] = useState(currentLocation.hazard);
  const [devModeOpen, setDevModeOpen] = useState(false);

  useEffect(() => {
    api.indiaLocations().then(setLocations).catch(() => {});
  }, []);

  const stateObj = locations.find((s) => s.name === selectedState);
  const districts = stateObj?.districts ?? [];

  const handleLocationSave = () => {
    onLocationChange(selectedState, selectedDistrict, selectedHazard);
  };

  const agentEntries = Object.entries(agents).sort(
    (a, b) => {
      const order = ["intake", "situation_analysis", "commander", "weather", "medical", "shelter", "infrastructure", "knowledge", "allocation", "reflection", "communication"];
      return order.indexOf(a[0]) - order.indexOf(b[0]);
    }
  );

  return (
    <div className="page-content" style={{ background: "var(--color-bg)" }}>
      <div
        style={{
          maxWidth: 560,
          margin: "0 auto",
          padding: "20px 16px 32px",
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
        className="fade-in"
      >
        {/* Header */}
        <h2
          style={{
            margin: 0,
            fontSize: 22,
            fontWeight: 800,
            fontFamily: "var(--font-heading)",
            color: "var(--color-text)",
          }}
        >
          Settings & More
        </h2>

        {/* ── Location Settings ───────────────────────────────── */}
        <div className="card" style={{ padding: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <span style={{ fontSize: 18 }}>📍</span>
            <span style={{ fontSize: 15, fontWeight: 700, color: "var(--color-text)" }}>
              Location Settings
            </span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {/* State */}
            <div>
              <label
                style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-secondary)", marginBottom: 4 }}
              >
                State / UT
              </label>
              <select
                value={selectedState}
                onChange={(e) => {
                  setSelectedState(e.target.value);
                  const st = locations.find((s) => s.name === e.target.value);
                  if (st?.districts?.[0]) setSelectedDistrict(st.districts[0].name);
                }}
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  borderRadius: 10,
                  border: "1px solid var(--color-border)",
                  background: "var(--color-bg-elevated)",
                  fontSize: 14,
                  color: "var(--color-text)",
                  fontWeight: 500,
                  outline: "none",
                }}
              >
                {locations.map((s) => (
                  <option key={s.code} value={s.name}>
                    {s.name} {s.type === "UT" ? "(UT)" : ""}
                  </option>
                ))}
              </select>
            </div>

            {/* District */}
            <div>
              <label
                style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-secondary)", marginBottom: 4 }}
              >
                District
              </label>
              <select
                value={selectedDistrict}
                onChange={(e) => setSelectedDistrict(e.target.value)}
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  borderRadius: 10,
                  border: "1px solid var(--color-border)",
                  background: "var(--color-bg-elevated)",
                  fontSize: 14,
                  color: "var(--color-text)",
                  fontWeight: 500,
                  outline: "none",
                }}
              >
                {districts.map((d) => (
                  <option key={d.name} value={d.name}>{d.name}</option>
                ))}
              </select>
            </div>

            {/* Hazard */}
            <div>
              <label
                style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-secondary)", marginBottom: 4 }}
              >
                Primary Hazard
              </label>
              <select
                value={selectedHazard}
                onChange={(e) => setSelectedHazard(e.target.value)}
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  borderRadius: 10,
                  border: "1px solid var(--color-border)",
                  background: "var(--color-bg-elevated)",
                  fontSize: 14,
                  color: "var(--color-text)",
                  fontWeight: 500,
                  outline: "none",
                }}
              >
                {HAZARDS.map((h) => (
                  <option key={h.value} value={h.value}>{h.label}</option>
                ))}
              </select>
            </div>

            <button
              className="btn-primary"
              onClick={handleLocationSave}
              style={{ marginTop: 4 }}
            >
              Update Location
            </button>
          </div>
        </div>

        {/* ── Emergency Contacts ──────────────────────────────── */}
        <div className="card" style={{ padding: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <span style={{ fontSize: 18 }}>📞</span>
            <span style={{ fontSize: 15, fontWeight: 700, color: "var(--color-text)" }}>
              Emergency Contacts
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[
              { name: "National Emergency", number: "112" },
              { name: "Disaster Management (NDMA)", number: "1070" },
              { name: "District Control Room", number: "1077" },
              { name: "Ambulance", number: "108" },
              { name: "Fire Services", number: "101" },
              { name: "Women Helpline", number: "181" },
              { name: "Child Helpline", number: "1098" },
            ].map((c) => (
              <a
                key={c.number}
                href={`tel:${c.number}`}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "8px 0",
                  borderBottom: "1px solid var(--color-border-light)",
                  textDecoration: "none",
                }}
              >
                <span style={{ fontSize: 14, color: "var(--color-text)" }}>{c.name}</span>
                <span style={{ fontSize: 14, fontWeight: 800, color: "var(--color-primary)" }}>{c.number}</span>
              </a>
            ))}
          </div>
        </div>

        {/* ── About ───────────────────────────────────────────── */}
        <div className="card" style={{ padding: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: 18 }}>🛡️</span>
            <span style={{ fontSize: 15, fontWeight: 700, color: "var(--color-text)" }}>
              About SentinelAI
            </span>
          </div>
          <p style={{ margin: 0, fontSize: 13, color: "var(--color-text-secondary)", lineHeight: 1.5 }}>
            SentinelAI is an AI-powered emergency companion that helps citizens during natural disasters.
            It uses multiple specialized AI agents — Weather, Medical, Shelter, Infrastructure, and Government Knowledge —
            to provide personalized, actionable guidance in seconds.
          </p>
          <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 6 }}>
            <span className="badge badge-info">Gemini 2.0 Flash</span>
            <span className="badge badge-info">LangGraph</span>
            <span className="badge badge-info">ChromaDB RAG</span>
            <span className="badge badge-info">OpenStreetMap</span>
          </div>
        </div>

        {/* ── Developer Mode (Hidden for Judges) ──────────────── */}
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <button
            onClick={() => setDevModeOpen(!devModeOpen)}
            style={{
              width: "100%",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "14px 16px",
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: 14,
              fontWeight: 700,
              color: "var(--color-text-muted)",
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span>🧑‍💻</span> Developer Mode
            </span>
            <span style={{ fontSize: 12, transform: devModeOpen ? "rotate(180deg)" : "rotate(0)", transition: "transform 0.2s ease" }}>
              ▼
            </span>
          </button>

          {devModeOpen && (
            <div style={{ padding: "0 16px 16px", borderTop: "1px solid var(--color-border)" }} className="slide-up">
              <p style={{ margin: "12px 0 8px", fontSize: 11, fontWeight: 700, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Agentic AI Workflow — LangGraph Pattern 5
              </p>

              {/* System Status */}
              {status && (
                <div style={{ marginBottom: 12, padding: "10px 12px", background: "var(--color-bg-elevated)", borderRadius: 10 }}>
                  <p style={{ margin: "0 0 6px", fontSize: 12, fontWeight: 700, color: "var(--color-text)" }}>
                    System Status
                  </p>
                  <div style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11, color: "var(--color-text-secondary)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>LLM</span>
                      <span style={{ fontWeight: 700, color: status.llm.available ? "var(--color-safe)" : "var(--color-danger)" }}>
                        {status.llm.available ? "LIVE" : "FALLBACK"}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>RAG ({status.retrieval.detail})</span>
                      <span style={{ fontWeight: 700, color: status.retrieval.available ? "var(--color-safe)" : "var(--color-danger)" }}>
                        {status.retrieval.available ? "LIVE" : "OFF"}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>Vision Ensemble</span>
                      <span style={{ fontWeight: 700, color: status.vision.available ? "var(--color-safe)" : "var(--color-danger)" }}>
                        {status.vision.available ? "LIVE" : "OFF"}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Agent Workflow Pipeline */}
              {agentEntries.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {agentEntries.map(([role, agent], i) => {
                    const statusColor =
                      agent.status === "completed" ? "var(--color-safe)"
                        : agent.status === "running" ? "var(--color-primary)"
                          : agent.status === "failed" ? "var(--color-danger)"
                            : agent.status === "degraded" ? "var(--color-warning)"
                              : agent.status === "skipped" ? "var(--color-text-muted)"
                                : "var(--color-border)";

                    return (
                      <div key={role}>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 10,
                            padding: "8px 12px",
                            background: "var(--color-bg-elevated)",
                            borderRadius: 8,
                            borderLeft: `3px solid ${statusColor}`,
                          }}
                        >
                          <span
                            style={{
                              width: 8,
                              height: 8,
                              borderRadius: "50%",
                              background: statusColor,
                              flexShrink: 0,
                            }}
                          />
                          <div style={{ flex: 1 }}>
                            <span style={{ fontSize: 12, fontWeight: 700, color: "var(--color-text)" }}>
                              {(AGENT_LABEL as any)[role] || role}
                            </span>
                            {agent.lastTitle && (
                              <span style={{ fontSize: 11, color: "var(--color-text-muted)", marginLeft: 8 }}>
                                — {agent.lastTitle}
                              </span>
                            )}
                          </div>
                          <span
                            style={{
                              fontSize: 10,
                              fontWeight: 800,
                              color: statusColor,
                              textTransform: "uppercase",
                            }}
                          >
                            {agent.status}
                          </span>
                        </div>
                        {i < agentEntries.length - 1 && (
                          <div style={{ display: "flex", justifyContent: "center", padding: "2px 0" }}>
                            <span style={{ fontSize: 10, color: "var(--color-border)" }}>↓</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)", fontStyle: "italic" }}>
                  No active agent workflow. Press "I NEED HELP" to trigger the multi-agent pipeline.
                </p>
              )}

              {/* Trace Log Preview */}
              {traces.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <p style={{ margin: "0 0 6px", fontSize: 11, fontWeight: 700, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    Recent Trace Events ({traces.length})
                  </p>
                  <div
                    style={{
                      maxHeight: 200,
                      overflowY: "auto",
                      background: "#1E293B",
                      borderRadius: 8,
                      padding: 10,
                      fontFamily: "monospace",
                      fontSize: 10,
                      lineHeight: 1.6,
                      color: "#94A3B8",
                    }}
                  >
                    {traces.slice(-15).map((t) => (
                      <div key={t.event_id}>
                        <span style={{ color: "#64748B" }}>
                          [{new Date(t.timestamp).toLocaleTimeString("en-GB", { hour12: false })}]
                        </span>{" "}
                        <span style={{ color: "#22D3EE", fontWeight: 700 }}>{t.agent}</span>{" "}
                        <span style={{ color: "#CBD5E1" }}>{t.event_type}</span>{" "}
                        <span style={{ color: "#94A3B8" }}>{t.title}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Version */}
        <p style={{ textAlign: "center", fontSize: 11, color: "var(--color-text-muted)", margin: "8px 0 0" }}>
          SentinelAI v2.0 • Predict · Protect · Respond
        </p>
      </div>
    </div>
  );
}
