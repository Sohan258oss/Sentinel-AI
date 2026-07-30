import { useEffect, useState } from "react";
import { api } from "../lib/api";

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

interface Props {
  onSelectLocation: (state: string, district: string, hazard: string, districtData: any) => void;
  disabled?: boolean;
}

const HAZARD_OPTIONS = [
  { value: "flood", label: "🌊 Flood" },
  { value: "urban_flood", label: "🏙️ Urban Waterlogging" },
  { value: "cyclone", label: "🌀 Tropical Cyclone" },
  { value: "earthquake", label: "🏚️ Earthquake" },
  { value: "landslide", label: "⛰️ Landslide" },
  { value: "heatwave", label: "☀️ Heatwave" },
  { value: "building_collapse", label: "🏢 Building Collapse" },
  { value: "wildfire", label: "🔥 Wildfire" },
  { value: "industrial_chemical", label: "☣️ Industrial Chemical" },
];

export function LocationSelector({ onSelectLocation, disabled }: Props) {
  const [locations, setLocations] = useState<LocationState[]>([]);
  const [selectedState, setSelectedState] = useState<string>("Assam");
  const [selectedDistrict, setSelectedDistrict] = useState<string>("Kamrup Metropolitan");
  const [selectedHazard, setSelectedHazard] = useState<string>("flood");
  const [autoDetected, setAutoDetected] = useState<boolean>(false);
  const [detectingGps, setDetectingGps] = useState<boolean>(true);
  const [manualOverride, setManualOverride] = useState<boolean>(false);

  useEffect(() => {
    // 1. Fetch All-India locations dataset
    api.indiaLocations()
      .then((data) => {
        setLocations(data);

        // 2. Attempt Automatic Browser Geolocation
        if ("geolocation" in navigator) {
          navigator.geolocation.getCurrentPosition(
            async (position) => {
              const { latitude, longitude } = position.coords;
              try {
                const nearest = await api.nearestLocation(latitude, longitude);
                if (nearest && nearest.state && nearest.district) {
                  setSelectedState(nearest.state);
                  setSelectedDistrict(nearest.district);
                  setAutoDetected(true);
                  setDetectingGps(false);

                  const st = data.find((s) => s.name === nearest.state);
                  const dist = st?.districts.find((d) => d.name === nearest.district);
                  const hazard = dist?.primary_hazard || "flood";
                  setSelectedHazard(hazard);

                  // Auto-trigger guidance loading for user's exact detected location
                  onSelectLocation(nearest.state, nearest.district, hazard, dist || nearest);
                  return;
                }
              } catch {
                /* fallback below */
              }
              setDetectingGps(false);
            },
            () => {
              setDetectingGps(false);
            },
            { timeout: 6000 }
          );
        } else {
          setDetectingGps(false);
        }

        // Default initial trigger if GPS is disabled or pending
        if (data.length > 0) {
          const defaultSt = data.find((s) => s.name === "Assam") || data[0];
          if (defaultSt.districts.length > 0) {
            const firstDist = defaultSt.districts[0];
            onSelectLocation(defaultSt.name, firstDist.name, firstDist.primary_hazard || "flood", firstDist);
          }
        }
      })
      .catch(() => {
        setDetectingGps(false);
      });
  }, []);

  const currentStates = locations.find((s) => s.name === selectedState);
  const currentDistricts = currentStates?.districts || [];
  const currentDistData = currentDistricts.find((d) => d.name === selectedDistrict);

  const handleStateChange = (stateName: string) => {
    setSelectedState(stateName);
    setAutoDetected(false);
    const st = locations.find((s) => s.name === stateName);
    if (st && st.districts.length > 0) {
      const firstDist = st.districts[0];
      setSelectedDistrict(firstDist.name);
      setSelectedHazard(firstDist.primary_hazard || "flood");
      onSelectLocation(stateName, firstDist.name, firstDist.primary_hazard || "flood", firstDist);
    }
  };

  const handleDistrictChange = (distName: string) => {
    setSelectedDistrict(distName);
    setAutoDetected(false);
    const dist = currentDistricts.find((d) => d.name === distName);
    const hazard = dist?.primary_hazard || selectedHazard;
    if (dist && dist.primary_hazard) {
      setSelectedHazard(dist.primary_hazard);
    }
    onSelectLocation(selectedState, distName, hazard, dist);
  };

  const handleHazardChange = (hazardValue: string) => {
    setSelectedHazard(hazardValue);
    onSelectLocation(selectedState, selectedDistrict, hazardValue, currentDistData);
  };

  return (
    <div className="rounded-xl border border-signal/40 bg-panel/95 p-3.5 shadow-2xl backdrop-blur-md transition-all">
      {/* Location Status Header */}
      <div className="flex items-center justify-between border-b border-edge/60 pb-2 mb-3">
        <div className="flex items-center gap-2">
          {detectingGps ? (
            <span className="flex items-center gap-1.5 font-mono text-[10.5px] font-bold text-signal animate-pulse">
              <span className="size-2.5 rounded-full bg-signal" />
              <span>Detecting Your Real-Time GPS Location…</span>
            </span>
          ) : autoDetected ? (
            <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-0.5 font-mono text-[10.5px] font-extrabold text-emerald-400">
              <span className="size-2 rounded-full bg-emerald-400 animate-pulse" />
              🎯 GPS Auto-Detected Location: {selectedDistrict}, {selectedState}
            </span>
          ) : (
            <span className="font-mono text-[11px] font-bold uppercase tracking-wider text-signal flex items-center gap-1.5">
              📍 Current Selected Location: {selectedDistrict}, {selectedState}
            </span>
          )}
        </div>

        <button
          onClick={() => setManualOverride((v) => !v)}
          className="rounded border border-edge-bright bg-abyss px-2.5 py-1 font-mono text-[10px] font-bold text-ink-dim hover:text-signal hover:border-signal transition-all"
        >
          {manualOverride ? "✕ Close Selector" : "⚙️ Change Location"}
        </button>
      </div>

      {/* Dropdown selectors — visible if manual override requested or not yet auto-detected */}
      {(manualOverride || !autoDetected) && (
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
          {/* State Dropdown */}
          <div>
            <label className="block font-mono text-[9.5px] font-bold uppercase tracking-wider text-ink-dim mb-1">
              1. Select State / UT
            </label>
            <select
              value={selectedState}
              onChange={(e) => handleStateChange(e.target.value)}
              disabled={disabled}
              className="w-full rounded-lg border border-edge/80 bg-abyss/90 px-2.5 py-1.5 font-mono text-xs font-semibold text-ink focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
            >
              {locations.map((st) => (
                <option key={st.code} value={st.name}>
                  {st.name} ({st.type})
                </option>
              ))}
            </select>
          </div>

          {/* District Dropdown */}
          <div>
            <label className="block font-mono text-[9.5px] font-bold uppercase tracking-wider text-ink-dim mb-1">
              2. Select District
            </label>
            <select
              value={selectedDistrict}
              onChange={(e) => handleDistrictChange(e.target.value)}
              disabled={disabled || currentDistricts.length === 0}
              className="w-full rounded-lg border border-edge/80 bg-abyss/90 px-2.5 py-1.5 font-mono text-xs font-semibold text-ink focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
            >
              {currentDistricts.map((d) => (
                <option key={d.name} value={d.name}>
                  {d.name} ({d.hq})
                </option>
              ))}
            </select>
          </div>

          {/* Disaster Type */}
          <div>
            <label className="block font-mono text-[9.5px] font-bold uppercase tracking-wider text-ink-dim mb-1">
              3. Disaster / Hazard Type
            </label>
            <select
              value={selectedHazard}
              onChange={(e) => handleHazardChange(e.target.value)}
              disabled={disabled}
              className="w-full rounded-lg border border-edge/80 bg-abyss/90 px-2.5 py-1.5 font-mono text-xs font-semibold text-ink focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
            >
              {HAZARD_OPTIONS.map((h) => (
                <option key={h.value} value={h.value}>
                  {h.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
    </div>
  );
}
