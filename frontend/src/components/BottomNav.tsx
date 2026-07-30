export type TabKey = "home" | "map" | "assistant" | "alerts" | "more";

interface Props {
  activeTab: TabKey;
  onTabChange: (tab: TabKey) => void;
}

const TABS: { key: TabKey; icon: string; label: string }[] = [
  { key: "home", icon: "🏠", label: "Home" },
  { key: "map", icon: "🗺️", label: "Map" },
  { key: "assistant", icon: "🤖", label: "AI" },
  { key: "alerts", icon: "🚨", label: "Alerts" },
  { key: "more", icon: "⚙️", label: "More" },
];

export function BottomNav({ activeTab, onTabChange }: Props) {
  return (
    <nav className="bottom-nav" role="tablist">
      {TABS.map((tab) => (
        <button
          key={tab.key}
          role="tab"
          aria-selected={activeTab === tab.key}
          className={`nav-tab ${activeTab === tab.key ? "active" : ""}`}
          onClick={() => onTabChange(tab.key)}
        >
          <span className="nav-tab-icon">{tab.icon}</span>
          <span className="nav-tab-label">{tab.label}</span>
        </button>
      ))}
    </nav>
  );
}
