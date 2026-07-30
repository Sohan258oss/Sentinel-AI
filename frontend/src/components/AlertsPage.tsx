import { useMemo } from "react";
import type { AgentTrace, NewsArticle } from "../lib/types";

interface Props {
  traces: AgentTrace[];
  running: boolean;
  picture: any;
  currentLocation: { state: string; district: string; hazard: string };
}

export function AlertsPage({ traces, running, picture, currentLocation }: Props) {
  // Extract news from traces
  const { newsArticles, informationGap } = useMemo(() => {
    const newsTrace = traces.find(
      (t) =>
        t.event_type === "tool_result" &&
        t.tool_invocation?.tool_name === "search_news"
    );
    if (!newsTrace) return { newsArticles: [] as NewsArticle[], informationGap: null };

    const result = newsTrace.payload?.result as Record<string, unknown> | undefined;
    if (!result) return { newsArticles: [] as NewsArticle[], informationGap: null };

    const articles = (result.articles as NewsArticle[] | undefined) ?? [];
    const gap =
      result.feed_available === false
        ? (result.information_gap as string | null) ?? null
        : null;

    return { newsArticles: articles, informationGap: gap };
  }, [traces]);

  // Extract advisory from picture (only if location matches current selected location)
  const isLocationMatch = picture?.report?.location?.district
    ? picture.report.location.district.toLowerCase() === currentLocation.district.toLowerCase()
    : false;

  const assessment = isLocationMatch ? picture?.assessment : null;
  const communications = isLocationMatch ? picture?.communications : null;
  const publicAlert = communications?.public_alert_headline;

  return (
    <div className="page-content" style={{ background: "var(--color-bg)" }}>
      <div
        style={{
          maxWidth: 560,
          margin: "0 auto",
          padding: "20px 16px",
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
        className="fade-in"
      >
        {/* Header */}
        <div>
          <h2
            style={{
              margin: 0,
              fontSize: 22,
              fontWeight: 800,
              fontFamily: "var(--font-heading)",
              color: "var(--color-text)",
            }}
          >
            Alerts & Advisories
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--color-text-secondary)" }}>
            {currentLocation.district}, {currentLocation.state}
          </p>
        </div>

        {/* Active Incident */}
        {running && (
          <div
            className="card"
            style={{
              padding: "14px 16px",
              borderLeft: "4px solid var(--color-primary)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="pulse-ring" style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: "var(--color-primary)",
                display: "inline-block",
              }} />
              <span style={{ fontSize: 14, fontWeight: 700, color: "var(--color-primary)" }}>
                AI Agents Analyzing Your Area...
              </span>
            </div>
            <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--color-text-secondary)" }}>
              Sentinel AI is gathering real-time data from weather, medical, shelter, and infrastructure agents.
            </p>
          </div>
        )}

        {/* Government Advisory */}
        {publicAlert && (
          <div
            className="card"
            style={{
              padding: "14px 16px",
              borderLeft: "4px solid var(--color-warning)",
              background: "var(--color-warning-light)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 16 }}>🏛️</span>
              <span style={{ fontSize: 12, fontWeight: 700, color: "#92400E" }}>
                GOVERNMENT ADVISORY
              </span>
            </div>
            <p style={{ margin: 0, fontSize: 14, fontWeight: 600, color: "#78350F", lineHeight: 1.5 }}>
              {publicAlert}
            </p>
          </div>
        )}

        {/* Situation Assessment */}
        {assessment && (
          <div className="card" style={{ padding: "14px 16px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              <span style={{ fontSize: 16 }}>📊</span>
              <span style={{ fontSize: 14, fontWeight: 700, color: "var(--color-text)" }}>
                Situation Assessment
              </span>
            </div>
            <p style={{ margin: "0 0 10px", fontSize: 14, color: "var(--color-text)", fontWeight: 600 }}>
              {assessment.headline}
            </p>
            <p style={{ margin: 0, fontSize: 13, color: "var(--color-text-secondary)", lineHeight: 1.5 }}>
              {assessment.summary}
            </p>
            {assessment.immediate_risks?.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <p style={{ margin: "0 0 6px", fontSize: 12, fontWeight: 700, color: "var(--color-danger)" }}>
                  Immediate Risks:
                </p>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {assessment.immediate_risks.map((risk: string, i: number) => (
                    <li
                      key={i}
                      style={{ fontSize: 13, color: "var(--color-text-secondary)", marginBottom: 3 }}
                    >
                      {risk}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* AI News Briefing — Summarized Bullet Points */}
        {newsArticles.length > 0 && (
          <div className="card" style={{ padding: "14px 16px" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 18 }}>📰</span>
                <span style={{ fontSize: 14, fontWeight: 700, color: "var(--color-text)", fontFamily: "var(--font-heading)" }}>
                  District OSINT News Briefing
                </span>
              </div>
              <span style={{ fontSize: 10, fontWeight: 700, color: "var(--color-primary)", background: "var(--color-primary-light)", padding: "2px 8px", borderRadius: 999 }}>
                AI SUMMARIZED
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {newsArticles.slice(0, 4).map((article, i) => {
                const cleanHeadline = article.title.replace(/\s*-\s*[^-]+$/, "").trim();
                return (
                  <div
                    key={i}
                    style={{
                      display: "flex",
                      gap: 10,
                      alignItems: "flex-start",
                      padding: "8px 10px",
                      background: "var(--color-bg-elevated)",
                      borderRadius: 8,
                    }}
                  >
                    <span style={{ color: "var(--color-primary)", fontWeight: 900, fontSize: 14 }}>•</span>
                    <div style={{ flex: 1 }}>
                      <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: "var(--color-text)", lineHeight: 1.4 }}>
                        {cleanHeadline}
                      </p>
                      <div style={{ display: "flex", gap: 8, marginTop: 4, fontSize: 10, color: "var(--color-text-muted)", fontWeight: 600 }}>
                        {article.source && <span>Source: {article.source}</span>}
                        {article.published_at && (
                          <span>
                            • {new Date(article.published_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Information Gap Notice */}
        {informationGap && newsArticles.length === 0 && (
          <div className="card" style={{ padding: "14px 16px", textAlign: "center" }}>
            <span style={{ fontSize: 28, display: "block", marginBottom: 8 }}>📡</span>
            <p style={{ margin: 0, fontSize: 14, fontWeight: 600, color: "var(--color-text-secondary)" }}>
              {informationGap}
            </p>
            <p style={{ margin: "6px 0 0", fontSize: 12, color: "var(--color-text-muted)" }}>
              Monitoring official channels for updates.
            </p>
          </div>
        )}

        {/* Empty State */}
        {!running && !assessment && newsArticles.length === 0 && !informationGap && (
          <div className="card" style={{ padding: 32, textAlign: "center" }}>
            <span style={{ fontSize: 36, display: "block", marginBottom: 12 }}>✅</span>
            <p style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "var(--color-text)" }}>
              No Active Alerts
            </p>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: "var(--color-text-secondary)" }}>
              Your area is currently safe. Press "I NEED HELP" on the Home tab to get instant emergency guidance.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
