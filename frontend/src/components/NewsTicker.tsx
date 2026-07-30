/**
 * NewsTicker — horizontal auto-scrolling news headline banner.
 *
 * Inspired by World Monitor's bottom news band. Articles are extracted from the
 * search_news tool_result payload in the live trace stream. The ticker pauses
 * when the user hovers over it so they can read the headline.
 */
import type { NewsArticle } from "../lib/types";

interface Props {
  articles: NewsArticle[];
  running: boolean;
  /** Colour to tint the ticker accent based on incident severity */
  severityColor?: string;
}

export function NewsTicker({ articles, running, severityColor = "#22d3ee" }: Props) {
  // Build the scrolling text items
  const items: { label: string; source: string }[] =
    articles.length > 0
      ? articles.map((a) => ({
          label: a.title,
          source: a.source ?? "Unknown",
        }))
      : running
        ? [{ label: "Awaiting OSINT intelligence feed from NewsAPI…", source: "SENTINEL" }]
        : [];

  if (items.length === 0) return null;

  // Duplicate items so the scroll loop is seamless
  const doubled = [...items, ...items];

  return (
    <div
      className="flex items-center overflow-hidden border-t border-edge bg-void/90 backdrop-blur-sm"
      style={{ height: "28px" }}
    >
      {/* Left badge */}
      <div
        className="flex shrink-0 items-center gap-1.5 border-r border-edge px-2.5"
        style={{ height: "100%", borderColor: `${severityColor}40` }}
      >
        <span
          className="size-1.5 rounded-full"
          style={{ background: severityColor, boxShadow: `0 0 6px ${severityColor}` }}
        />
        <span
          className="font-mono text-[9px] font-bold tracking-widest uppercase"
          style={{ color: severityColor }}
        >
          OSINT FEED
        </span>
      </div>

      {/* Scrolling track */}
      <div className="relative min-w-0 flex-1 overflow-hidden">
        <div
          className="flex whitespace-nowrap"
          style={{
            animation: "ticker-scroll 40s linear infinite",
            animationPlayState: "running",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.animationPlayState = "paused";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.animationPlayState = "running";
          }}
        >
          {doubled.map((item, i) => (
            <span key={i} className="inline-flex items-center gap-2 px-6">
              <span className="font-mono text-[9.5px] font-medium text-ink">
                {item.label}
              </span>
              <span className="font-mono text-[8.5px] text-ink-faint">
                [{item.source}]
              </span>
              <span className="text-edge-bright">·</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
