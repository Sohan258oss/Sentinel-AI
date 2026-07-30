/**
 * NewsPanel — glassmorphic floating panel for OSINT news articles.
 *
 * Appears as a right-side overlay on the map when the search_news tool
 * returns live articles. Each card shows: headline, source badge,
 * publish time, and a 2-line snippet. Style inspired by World Monitor's
 * event detail panels.
 */
import type { NewsArticle } from "../lib/types";

interface Props {
  articles: NewsArticle[];
  isOpen: boolean;
  onClose: () => void;
  incidentName?: string;
  hazardType?: string;
  severityColor?: string;
  informationGap?: string | null;
  isMinimized?: boolean;
  onMinimizeToggle?: () => void;
}

function timeAgo(isoString: string | null): string {
  if (!isoString) return "Unknown time";
  const date = new Date(isoString);
  const now = Date.now();
  const diffMs = now - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  return `${Math.floor(diffHrs / 24)}d ago`;
}

export function NewsPanel({
  articles,
  isOpen,
  onClose,
  incidentName,
  hazardType,
  severityColor = "#22d3ee",
  informationGap,
  isMinimized = false,
  onMinimizeToggle,
}: Props) {
  if (!isOpen) return null;

  if (isMinimized) {
    return (
      <div
        className="pointer-events-auto flex items-center gap-2 rounded-lg border px-3 py-1.5 shadow-2xl backdrop-blur-md transition-all cursor-pointer hover:border-signal"
        style={{
          background: "rgba(8, 11, 20, 0.90)",
          borderColor: `${severityColor}60`,
        }}
        onClick={onMinimizeToggle}
      >
        <span className="size-2 rounded-full pulse-ring" style={{ background: severityColor }} />
        <span className="font-mono text-[10px] font-bold uppercase tracking-wider" style={{ color: severityColor }}>
          OSINT News ({articles.length})
        </span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onMinimizeToggle?.();
          }}
          title="Expand OSINT Panel"
          className="ml-2 font-mono text-[11px] text-ink-faint hover:text-ink"
        >
          ▲
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onClose();
          }}
          title="Close Panel"
          className="ml-1 font-mono text-[11px] text-ink-faint hover:text-ink"
        >
          ✕
        </button>
      </div>
    );
  }

  return (
    <div
      className="pointer-events-auto flex flex-col overflow-hidden rounded-lg border shadow-2xl transition-all"
      style={{
        width: "320px",
        maxHeight: "520px",
        background: "rgba(8, 11, 20, 0.85)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        borderColor: `${severityColor}40`,
        boxShadow: `0 0 40px ${severityColor}15, 0 20px 60px rgba(0,0,0,0.6)`,
      }}
    >
      {/* Header */}
      <div
        className="flex shrink-0 items-center gap-2 px-3 py-2.5"
        style={{
          borderBottom: `1px solid ${severityColor}30`,
          background: `linear-gradient(90deg, ${severityColor}12, transparent)`,
        }}
      >
        <span
          className="size-2 rounded-full pulse-ring"
          style={{ background: severityColor }}
        />
        <div className="min-w-0 flex-1">
          <div className="font-mono text-[10px] font-bold tracking-widest uppercase" style={{ color: severityColor }}>
            OSINT — Live News Intelligence
          </div>
          {incidentName && (
            <div className="truncate font-mono text-[9px] text-ink-faint">
              {hazardType ? `${hazardType.toUpperCase()} · ` : ""}{incidentName}
            </div>
          )}
        </div>
        <div className="ml-auto flex items-center gap-1 shrink-0">
          {onMinimizeToggle && (
            <button
              onClick={onMinimizeToggle}
              title="Minimize Panel"
              className="rounded p-1 font-mono text-[11px] text-ink-faint hover:bg-edge hover:text-ink transition-colors"
            >
              ─
            </button>
          )}
          <button
            onClick={onClose}
            title="Close Panel"
            className="rounded p-1 font-mono text-[11px] text-ink-faint hover:bg-edge hover:text-ink transition-colors"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Article count badge */}
      <div className="shrink-0 border-b border-edge px-3 py-1.5">
        {articles.length > 0 ? (
          <span className="font-mono text-[9px] text-ink-dim">
            <span className="font-bold" style={{ color: severityColor }}>{articles.length}</span>
            {" "}articles · last 24h
          </span>
        ) : (
          <span className="font-mono text-[9px] text-amber-400">
            ⚠ No live articles retrieved
          </span>
        )}
      </div>

      {/* Articles */}
      <div className="flex-1 overflow-y-auto">
        {articles.length > 0 ? (
          <div className="divide-y divide-edge/50">
            {articles.map((article, i) => (
              <div
                key={i}
                className="group px-3 py-2.5 transition-colors hover:bg-white/5"
              >
                {/* Source & time row */}
                <div className="mb-1 flex items-center gap-1.5">
                  <span
                    className="rounded px-1.5 py-px font-mono text-[8px] font-bold uppercase"
                    style={{
                      background: `${severityColor}20`,
                      color: severityColor,
                    }}
                  >
                    {article.source ?? "Unknown"}
                  </span>
                  <span className="font-mono text-[8.5px] text-ink-faint">
                    {timeAgo(article.published_at)}
                  </span>
                </div>

                {/* Headline */}
                {article.url ? (
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block text-[11px] font-semibold leading-snug text-ink hover:underline"
                    style={{ textDecorationColor: severityColor }}
                  >
                    {article.title}
                  </a>
                ) : (
                  <p className="text-[11px] font-semibold leading-snug text-ink">
                    {article.title}
                  </p>
                )}

                {/* Snippet */}
                {article.snippet && (
                  <p className="mt-1 line-clamp-2 text-[10px] leading-snug text-ink-faint">
                    {article.snippet}
                  </p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="px-3 py-4">
            <div className="rounded border border-amber-500/20 bg-amber-500/5 p-3">
              <p className="font-mono text-[9px] font-bold uppercase text-amber-400">
                Information Gap
              </p>
              <p className="mt-1 text-[10px] leading-snug text-ink-dim">
                {informationGap ??
                  "No live news feed is configured. Set SENTINEL_NEWSAPI_KEY to enable OSINT corroboration."}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
