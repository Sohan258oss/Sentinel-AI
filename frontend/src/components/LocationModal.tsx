import { useEffect, useState } from "react";
import { api } from "../lib/api";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  currentLocation: { state: string; district: string; hazard: string };
  onSelectLocation: (state: string, district: string, lat: number, lon: number) => void;
}

interface StateData {
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

export function LocationModal({
  isOpen,
  onClose,
  currentLocation,
  onSelectLocation,
}: Props) {
  const [locations, setLocations] = useState<StateData[]>([]);
  const [selectedState, setSelectedState] = useState(currentLocation.state);
  const [selectedDistrict, setSelectedDistrict] = useState(currentLocation.district);
  const [detectingGps, setDetectingGps] = useState(false);

  useEffect(() => {
    api.indiaLocations().then(setLocations).catch(() => {});
  }, []);

  useEffect(() => {
    setSelectedState(currentLocation.state);
    setSelectedDistrict(currentLocation.district);
  }, [currentLocation]);

  if (!isOpen) return null;

  const stateObj = locations.find((s) => s.name === selectedState);
  const districts = stateObj?.districts ?? [];

  const handleGpsDetect = () => {
    if (!("geolocation" in navigator)) return;
    setDetectingGps(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const nearest = await api.nearestLocation(
            pos.coords.latitude,
            pos.coords.longitude
          );
          if (nearest?.state && nearest?.district) {
            onSelectLocation(
              nearest.state,
              nearest.district,
              nearest.lat || pos.coords.latitude,
              nearest.lon || pos.coords.longitude
            );
            onClose();
          }
        } catch {
          /* silent fallback */
        } finally {
          setDetectingGps(false);
        }
      },
      () => setDetectingGps(false),
      { timeout: 6000 }
    );
  };

  const handleApply = () => {
    const distObj = districts.find((d) => d.name === selectedDistrict);
    const lat = distObj?.lat ?? 26.1445;
    const lon = distObj?.lon ?? 91.7362;
    onSelectLocation(selectedState, selectedDistrict, lat, lon);
    onClose();
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        background: "rgba(15, 23, 42, 0.6)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
      className="fade-in"
      onClick={onClose}
    >
      <div
        className="card slide-up"
        style={{
          width: "100%",
          maxWidth: 420,
          padding: 20,
          background: "var(--color-bg-card)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
          }}
        >
          <h3
            style={{
              margin: 0,
              fontSize: 17,
              fontWeight: 800,
              fontFamily: "var(--font-heading)",
              color: "var(--color-text)",
            }}
          >
            📍 Set Your Location
          </h3>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              fontSize: 18,
              cursor: "pointer",
              color: "var(--color-text-muted)",
            }}
          >
            ✕
          </button>
        </div>

        {/* GPS Auto Detect */}
        <button
          className="btn-secondary"
          onClick={handleGpsDetect}
          disabled={detectingGps}
          style={{
            width: "100%",
            marginBottom: 16,
            borderColor: "var(--color-primary)",
            color: "var(--color-primary)",
            fontWeight: 700,
          }}
        >
          <span>🎯</span>
          <span>{detectingGps ? "Detecting GPS..." : "Auto-Detect My GPS Location"}</span>
        </button>

        <div style={{ textAlign: "center", fontSize: 11, color: "var(--color-text-muted)", margin: "0 0 14px", fontWeight: 700, letterSpacing: "0.05em" }}>
          ── OR SELECT MANUALLY ──
        </div>

        {/* State */}
        <div style={{ marginBottom: 12 }}>
          <label
            style={{
              display: "block",
              fontSize: 12,
              fontWeight: 600,
              color: "var(--color-text-secondary)",
              marginBottom: 4,
            }}
          >
            State / Union Territory
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
        <div style={{ marginBottom: 20 }}>
          <label
            style={{
              display: "block",
              fontSize: 12,
              fontWeight: 600,
              color: "var(--color-text-secondary)",
              marginBottom: 4,
            }}
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
              <option key={d.name} value={d.name}>
                {d.name}
              </option>
            ))}
          </select>
        </div>

        <button
          className="btn-primary"
          onClick={handleApply}
          style={{ width: "100%" }}
        >
          Apply Location
        </button>
      </div>
    </div>
  );
}
