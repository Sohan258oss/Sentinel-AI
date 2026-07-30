import { useEffect, useState } from "react";

interface Props {
  district: string;
  state: string;
  running: boolean;
  onOpenLocationModal?: () => void;
}

export function TopBar({ district, state: _state, running, onOpenLocationModal }: Props) {
  const [timeStr, setTimeStr] = useState("");

  useEffect(() => {
    const update = () =>
      setTimeStr(new Date().toLocaleTimeString("en-US", { hour12: true, hour: "numeric", minute: "2-digit" }));
    update();
    const id = setInterval(update, 30_000);
    return () => clearInterval(id);
  }, []);

  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        height: "var(--topbar-h)",
        padding: "0 16px",
        background: "var(--color-bg-card)",
        borderBottom: "1px solid var(--color-border)",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        position: "relative",
        zIndex: 40,
        flexShrink: 0,
      }}
    >
      {/* Brand */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: 8,
            background: "linear-gradient(135deg, #2563EB 0%, #0EA5E9 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "white",
            fontWeight: 900,
            fontSize: 13,
            fontFamily: "var(--font-heading)",
          }}
        >
          S
        </div>
        <div>
          <h1
            style={{
              margin: 0,
              fontSize: 16,
              fontWeight: 800,
              fontFamily: "var(--font-heading)",
              color: "var(--color-text)",
              letterSpacing: "-0.01em",
              lineHeight: 1.2,
            }}
          >
            Sentinel<span style={{ color: "var(--color-primary)" }}>AI</span>
          </h1>
          <p
            style={{
              margin: 0,
              fontSize: 10,
              color: "var(--color-text-muted)",
              fontWeight: 600,
              letterSpacing: "0.04em",
            }}
          >
            Predict · Protect · Respond
          </p>
        </div>
      </div>

      {/* Center — Location Badge (Clickable) */}
      <button
        onClick={onOpenLocationModal}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          background: "var(--color-bg-elevated)",
          border: "1px solid var(--color-border)",
          padding: "4px 10px",
          borderRadius: 999,
          cursor: "pointer",
          transition: "all 0.15s ease",
        }}
        title="Click to change location or auto-detect GPS"
      >
        <span style={{ fontSize: 13 }}>📍</span>
        <span
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: "var(--color-text)",
            maxWidth: 160,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {district}
        </span>
        <span style={{ fontSize: 10, color: "var(--color-text-muted)" }}>▼</span>
        {running && (
          <span
            className="pulse-ring"
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "var(--color-primary)",
              display: "inline-block",
            }}
          />
        )}
      </button>

      {/* Right — Time & Emergency */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <a
          href="tel:112"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 4,
            padding: "4px 10px",
            borderRadius: 999,
            background: "var(--color-emergency-light)",
            color: "var(--color-emergency)",
            fontSize: 11,
            fontWeight: 800,
            textDecoration: "none",
            transition: "all 0.15s ease",
          }}
        >
          📞 112
        </a>
        {timeStr && (
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "var(--color-text-muted)",
            }}
          >
            {timeStr}
          </span>
        )}
      </div>
    </header>
  );
}
