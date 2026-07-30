import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { getOfflineGuideline, OFFLINE_DISASTER_DATABASE, type DisasterGuideline } from "../lib/offlineSafetyStore";

interface Props {
  currentLocation: { state: string; district: string; hazard: string };
  districtIntelligenceData: any;
  onTriggerEmergency: (
    disasterKey: string,
    district: string,
    state: string,
    lat: number,
    lon: number
  ) => void;
  onLocationResolved: (state: string, district: string, lat: number, lon: number) => void;
  onOpenLocationModal?: () => void;
  running: boolean;
  picture: any;
}

const DISASTER_TYPES = [
  { key: "flood", icon: "🌊", label: "Flood" },
  { key: "cyclone", icon: "🌀", label: "Cyclone" },
  { key: "earthquake", icon: "🏚️", label: "Earthquake" },
  { key: "medical", icon: "🩹", label: "Medical" },
  { key: "shelter", icon: "⛺", label: "Shelter" },
  { key: "electrical", icon: "⚡", label: "Power" },
];

export function HomePage({
  currentLocation,
  districtIntelligenceData,
  onTriggerEmergency,
  onLocationResolved,
  onOpenLocationModal,
  running,
  picture,
}: Props) {
  const [detectingGps, setDetectingGps] = useState(true);
  const [selectedDisaster, setSelectedDisaster] = useState("flood");
  const [emergencyActivated, setEmergencyActivated] = useState(false);
  const [guideline, setGuideline] = useState<DisasterGuideline>(OFFLINE_DISASTER_DATABASE.flood);

  const distInfo = districtIntelligenceData?.district_info;
  const facilities = districtIntelligenceData?.facilities;
  const actionPlan = districtIntelligenceData?.action_plan;

  // GPS auto-detection on mount
  useEffect(() => {
    if (!("geolocation" in navigator)) {
      setDetectingGps(false);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const nearest = await api.nearestLocation(pos.coords.latitude, pos.coords.longitude);
          if (nearest?.state && nearest?.district) {
            onLocationResolved(nearest.state, nearest.district, nearest.lat, nearest.lon);
          }
        } catch { /* silent fallback */ }
        setDetectingGps(false);
      },
      () => setDetectingGps(false),
      { timeout: 5000 }
    );
  }, []);

  const handleDisasterSelect = (key: string) => {
    setSelectedDisaster(key);
    setGuideline(getOfflineGuideline(key));
  };

  const handleNeedHelp = () => {
    setEmergencyActivated(true);
    const lat = distInfo?.lat ?? 26.1445;
    const lon = distInfo?.lon ?? 91.7362;
    onTriggerEmergency(
      selectedDisaster,
      currentLocation.district,
      currentLocation.state,
      lat,
      lon
    );
  };

  // Determine risk level
  const severity = picture?.assessment?.severity;
  const riskMap: Record<string, { label: string; cls: string }> = {
    catastrophic: { label: "CRITICAL", cls: "badge-danger" },
    severe: { label: "SEVERE", cls: "badge-danger" },
    moderate: { label: "MODERATE", cls: "badge-warning" },
    minor: { label: "LOW", cls: "badge-safe" },
    informational: { label: "SAFE", cls: "badge-safe" },
  };
  const riskBadge = severity && riskMap[severity]
    ? riskMap[severity]
    : { label: "MONITORING", cls: "badge-info" };

  // Find nearest hospital & shelter
  const nearestHospital = facilities?.hospitals?.[0];
  const nearestShelter = facilities?.shelters?.[0];

  return (
    <div className="page-content" style={{ background: "var(--color-bg)" }}>
      <div
        style={{
          maxWidth: 480,
          margin: "0 auto",
          padding: "16px 16px 24px",
          display: "flex",
          flexDirection: "column",
          gap: 14,
        }}
        className="fade-in"
      >
        {/* ── Location & Weather (Clickable Location Card) ──────────────────────────────── */}
        <div
          className="card"
          onClick={onOpenLocationModal}
          style={{ padding: "14px 16px", cursor: "pointer", transition: "all 0.15s ease" }}
          title="Click to change location or detect GPS"
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                <span style={{ fontSize: 16 }}>📍</span>
                <span
                  style={{
                    fontSize: 14,
                    fontWeight: 700,
                    color: "var(--color-text)",
                    fontFamily: "var(--font-heading)",
                  }}
                >
                  {detectingGps ? "Detecting location..." : `${currentLocation.district}`}
                </span>
                <span style={{ fontSize: 11, color: "var(--color-primary)", fontWeight: 700 }}>
                  (Change ✏️)
                </span>
              </div>
              <span
                style={{
                  fontSize: 12,
                  color: "var(--color-text-secondary)",
                  fontWeight: 500,
                }}
              >
                {currentLocation.state}, India
              </span>
            </div>
            <span className={`badge ${riskBadge.cls}`}>
              <span
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  background: "currentColor",
                  display: "inline-block",
                }}
              />
              {riskBadge.label}
            </span>
          </div>
        </div>

        {/* ── Disaster Type Selection ────────────────────────── */}
        <div>
          <p
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: "var(--color-text-secondary)",
              marginBottom: 8,
              paddingLeft: 2,
            }}
          >
            What's happening?
          </p>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: 8,
            }}
          >
            {DISASTER_TYPES.map((d) => (
              <button
                key={d.key}
                onClick={() => handleDisasterSelect(d.key)}
                className="card-compact"
                style={{
                  padding: "12px 8px",
                  textAlign: "center",
                  cursor: "pointer",
                  background:
                    selectedDisaster === d.key
                      ? "var(--color-primary-light)"
                      : "var(--color-bg-card)",
                  borderColor:
                    selectedDisaster === d.key
                      ? "var(--color-primary)"
                      : "var(--color-border)",
                  transition: "all 0.15s ease",
                }}
              >
                <div style={{ fontSize: 24, marginBottom: 4 }}>{d.icon}</div>
                <div
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color:
                      selectedDisaster === d.key
                        ? "var(--color-primary)"
                        : "var(--color-text-secondary)",
                  }}
                >
                  {d.label}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* ── 🚨 I NEED HELP ─────────────────────────────────── */}
        <div style={{ padding: "8px 0" }}>
          <button
            className="btn-emergency"
            onClick={handleNeedHelp}
            disabled={running}
            style={running ? { opacity: 0.7, cursor: "wait", animation: "none" } : {}}
          >
            {running ? (
              <>
                <span className="typing-dot" style={{ background: "white" }} />
                <span>Agents analyzing...</span>
              </>
            ) : (
              <>
                <span style={{ fontSize: 24 }}>🚨</span>
                <span>I NEED HELP</span>
              </>
            )}
          </button>
        </div>

        {/* ── Emergency Activated: Action Plan ────────────────── */}
        {emergencyActivated && (actionPlan || guideline) && (
          <div className="card slide-up" style={{ padding: 16 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 12,
                paddingBottom: 12,
                borderBottom: "1px solid var(--color-border)",
              }}
            >
              <span style={{ fontSize: 20 }}>{guideline.icon}</span>
              <div>
                <h3
                  style={{
                    margin: 0,
                    fontSize: 16,
                    fontWeight: 700,
                    fontFamily: "var(--font-heading)",
                    color: "var(--color-text)",
                  }}
                >
                  {guideline.disaster}
                </h3>
                <p
                  style={{
                    margin: 0,
                    fontSize: 12,
                    color: "var(--color-text-secondary)",
                  }}
                >
                  Follow these steps immediately
                </p>
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {guideline.actions.map((action) => (
                <div
                  key={action.step}
                  style={{
                    display: "flex",
                    gap: 12,
                    alignItems: "flex-start",
                  }}
                >
                  <span
                    style={{
                      minWidth: 28,
                      height: 28,
                      borderRadius: "50%",
                      background: action.urgent
                        ? "var(--color-emergency)"
                        : "var(--color-primary)",
                      color: "white",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 13,
                      fontWeight: 800,
                      flexShrink: 0,
                    }}
                  >
                    {action.step}
                  </span>
                  <div>
                    <p
                      style={{
                        margin: 0,
                        fontSize: 14,
                        fontWeight: 700,
                        color: action.urgent ? "var(--color-emergency)" : "var(--color-text)",
                      }}
                    >
                      {action.title}
                    </p>
                    <p
                      style={{
                        margin: "2px 0 0",
                        fontSize: 13,
                        color: "var(--color-text-secondary)",
                        lineHeight: 1.45,
                      }}
                    >
                      {action.detail}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Nearest Facilities & Safe Routes ──────────────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          {/* Hospital */}
          <div className="card-compact" style={{ padding: "14px 12px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 18 }}>🏥</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: "var(--color-text-muted)" }}>
                    NEAREST HOSPITAL
                  </span>
                </div>
                {nearestHospital?.is_real_osm && (
                  <span style={{ fontSize: 9, fontWeight: 800, color: "#16A34A", background: "#DCFCE7", padding: "1px 5px", borderRadius: 4 }}>
                    LIVE OSM
                  </span>
                )}
              </div>
              <p
                style={{
                  margin: 0,
                  fontSize: 13,
                  fontWeight: 700,
                  color: "var(--color-text)",
                  lineHeight: 1.3,
                }}
              >
                {nearestHospital?.name || "District General Hospital"}
              </p>
              <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--color-text-secondary)", fontWeight: 500 }}>
                {nearestHospital?.distance_km
                  ? `${nearestHospital.distance_km.toFixed(1)} km · ~${Math.max(2, Math.round(nearestHospital.distance_km * 2.5))} mins drive`
                  : "Nearby · Emergency Care"}
              </p>
            </div>
            {nearestHospital?.lat && nearestHospital?.lon && (
              <a
                href={`https://www.google.com/maps/dir/?api=1&destination=${nearestHospital.lat},${nearestHospital.lon}&travelmode=driving`}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  marginTop: 10,
                  fontSize: 11,
                  fontWeight: 700,
                  color: "var(--color-primary)",
                  textDecoration: "none",
                }}
              >
                🗺️ Safe Route →
              </a>
            )}
          </div>

          {/* Shelter */}
          <div className="card-compact" style={{ padding: "14px 12px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 18 }}>⛺</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: "var(--color-text-muted)" }}>
                    NEAREST SHELTER
                  </span>
                </div>
                <span style={{ fontSize: 9, fontWeight: 800, color: "#2563EB", background: "#DBEAFE", padding: "1px 5px", borderRadius: 4 }}>
                  SAFE ZONE
                </span>
              </div>
              <p
                style={{
                  margin: 0,
                  fontSize: 13,
                  fontWeight: 700,
                  color: "var(--color-text)",
                  lineHeight: 1.3,
                }}
              >
                {nearestShelter?.name || "Multipurpose Disaster Shelter"}
              </p>
              <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--color-text-secondary)", fontWeight: 500 }}>
                {nearestShelter?.distance_km
                  ? `${nearestShelter.distance_km.toFixed(1)} km · ~${Math.max(3, Math.round(nearestShelter.distance_km * 3))} mins drive`
                  : "Nearby · Elevated Structure"}
              </p>
            </div>
            {nearestShelter?.lat && nearestShelter?.lon && (
              <a
                href={`https://www.google.com/maps/dir/?api=1&destination=${nearestShelter.lat},${nearestShelter.lon}&travelmode=driving`}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  marginTop: 10,
                  fontSize: 11,
                  fontWeight: 700,
                  color: "var(--color-primary)",
                  textDecoration: "none",
                }}
              >
                🗺️ Evacuation Route →
              </a>
            )}
          </div>
        </div>

        {/* ── Emergency Numbers ───────────────────────────────── */}
        <div className="card" style={{ padding: "14px 16px" }}>
          <p
            style={{
              margin: "0 0 10px",
              fontSize: 13,
              fontWeight: 700,
              color: "var(--color-text-secondary)",
            }}
          >
            Emergency Numbers
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {[
              { label: "Emergency", number: "112", icon: "📞" },
              { label: "Disaster Relief", number: "1070", icon: "🆘" },
              { label: "District Control", number: "1077", icon: "🏛️" },
              { label: "Ambulance", number: "108", icon: "🚑" },
            ].map((h) => (
              <a
                key={h.number}
                href={`tel:${h.number}`}
                className="card-compact"
                style={{
                  padding: "10px 12px",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  textDecoration: "none",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                <span style={{ fontSize: 16 }}>{h.icon}</span>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 800, color: "var(--color-primary)" }}>
                    {h.number}
                  </div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: "var(--color-text-muted)" }}>
                    {h.label}
                  </div>
                </div>
              </a>
            ))}
          </div>
        </div>

        {/* ── I'm Not Safe (SOS) ──────────────────────────────── */}
        <button
          className="btn-secondary"
          onClick={handleNeedHelp}
          style={{
            width: "100%",
            borderColor: "var(--color-emergency)",
            color: "var(--color-emergency)",
            fontWeight: 700,
          }}
        >
          <span>🆘</span>
          <span>I'm Not Safe — Show Emergency Info</span>
        </button>
      </div>
    </div>
  );
}
