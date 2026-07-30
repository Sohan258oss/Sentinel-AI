import { useEffect, useState, useRef } from "react";
import { formatNumber } from "../lib/format";
import type {
  AgentRole,
  AllocationPlan,
  GeoPoint,
  RegistryRecord,
  SituationAssessment,
} from "../lib/types";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";

/* ── Layer Configuration ─────────────────────────────────── */

type LayerKey = "hospitals" | "shelters" | "police_fire" | "river_gauges";

const LAYERS: { key: LayerKey; label: string; color: string; emoji: string; category: string }[] = [
  { key: "hospitals",    label: "🏥 Hospitals",        color: "#dc2626", emoji: "🏥", category: "Hospital" },
  { key: "shelters",     label: "⛺ Relief Shelters",   color: "#059669", emoji: "⛺", category: "Relief Shelter" },
  { key: "police_fire",  label: "🚔 Police & Fire",    color: "#d97706", emoji: "🚔", category: "Police / Fire Station" },
  { key: "river_gauges", label: "🌊 Flood Monitoring",  color: "#0891b2", emoji: "🌊", category: "Flood Monitoring Station" },
];

/* ── Helpers ──────────────────────────────────────────────── */

function haversineDist(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function googleMapsUrl(fromLat: number, fromLon: number, toLat: number, toLon: number): string {
  return `https://www.google.com/maps/dir/${fromLat},${fromLon}/${toLat},${toLon}`;
}

/* ── Props ────────────────────────────────────────────────── */

interface Props {
  mapboxToken?: string | null;
  incidentPoint?: GeoPoint | null;
  incidentName?: string;
  assessment?: SituationAssessment | null;
  allocationPlan?: AllocationPlan | null;
  activeAgentRole?: AgentRole | null;
  districtFacilities?: any;
  liveHospitals?: any[];
}

/* ── Component ────────────────────────────────────────────── */

export function TacticalMap({
  mapboxToken,
  incidentPoint,
  incidentName: _incidentName,
  assessment: _assessment,
  allocationPlan: _allocationPlan,
  activeAgentRole: _activeAgentRole,
  districtFacilities,
  liveHospitals,
}: Props) {

  /* ── Data State ── */
  const [data, setData] = useState<Record<LayerKey, RegistryRecord[]>>({
    hospitals: [],
    shelters: [],
    police_fire: [],
    river_gauges: [],
  });

  const [active, setActive] = useState<Record<LayerKey, boolean>>({
    hospitals: true,
    shelters: true,
    police_fire: true,
    river_gauges: true,
  });

  /* ── Refs ── */
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const markersRef = useRef<mapboxgl.Marker[]>([]);
  const popupsRef = useRef<mapboxgl.Popup[]>([]);

  /* ── Build facility data from props ── */
  useEffect(() => {
    const hospSource = liveHospitals && liveHospitals.length > 0
      ? liveHospitals
      : districtFacilities?.hospitals || [];

    const nextHospitals = hospSource.map((h: any) => ({
      name: h.name,
      point: { latitude: h.lat, longitude: h.lon },
      available_beds: h.available_beds ?? h.icu_available ?? 10,
      icu_available: h.icu_available ?? 4,
      address: h.address ?? "",
      contact: h.contact ?? "108",
      distance_km: h.distance_km ?? null,
    }));

    const nextShelters = (districtFacilities?.shelters || []).map((s: any) => ({
      name: s.name,
      point: {
        latitude: s.lat ?? (incidentPoint?.latitude ? incidentPoint.latitude + 0.01 : 13.09),
        longitude: s.lon ?? (incidentPoint?.longitude ? incidentPoint.longitude + 0.01 : 80.28),
      },
      capacity: s.capacity ?? 1000,
      current_occupancy: s.current_occupancy ?? 200,
      flood_safe: true,
      address: s.address ?? "",
      contact: s.contact ?? "1077",
      distance_km: s.distance_km ?? null,
    }));

    const nextPoliceFire = (districtFacilities?.police_fire || []).map((pf: any) => ({
      name: pf.name,
      point: {
        latitude: pf.lat ?? (incidentPoint?.latitude ? incidentPoint.latitude - 0.012 : 13.07),
        longitude: pf.lon ?? (incidentPoint?.longitude ? incidentPoint.longitude - 0.012 : 80.26),
      },
      organization: pf.name,
      type: pf.type ?? "police",
      contact: pf.contact ?? "112",
      distance_km: pf.distance_km ?? null,
    }));

    const baseLat = incidentPoint?.latitude || 13.08;
    const baseLon = incidentPoint?.longitude || 80.27;

    const nextGauges = [
      {
        name: "River Flood Monitor — Station Alpha",
        point: { latitude: baseLat + 0.02, longitude: baseLon - 0.015 },
        current_level_m: 8.4,
        warning_level_m: 7.5,
        danger_level_m: 9.0,
        station: "Alpha",
      },
      {
        name: "Flood Corridor Checkpoint — Beta",
        point: { latitude: baseLat - 0.025, longitude: baseLon + 0.02 },
        current_level_m: 5.2,
        warning_level_m: 6.0,
        danger_level_m: 7.5,
        station: "Beta",
      },
    ];

    setData({
      hospitals: nextHospitals,
      shelters: nextShelters,
      police_fire: nextPoliceFire,
      river_gauges: nextGauges,
    });
  }, [districtFacilities, liveHospitals, incidentPoint]);

  /* ── Initialize Mapbox ── */
  useEffect(() => {
    if (!mapboxToken || !mapContainerRef.current) return;

    mapboxgl.accessToken = mapboxToken;
    const center: [number, number] = incidentPoint
      ? [incidentPoint.longitude, incidentPoint.latitude]
      : [77.59, 12.97]; // Bengaluru fallback

    const mapInstance = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: "mapbox://styles/mapbox/streets-v12",
      center,
      zoom: 13,
      attributionControl: false,
    });

    mapInstance.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "bottom-right");

    mapInstance.on("load", () => {
      mapRef.current = mapInstance;
      // Trigger a re-render to place markers
      setActive((prev) => ({ ...prev }));
    });

    return () => {
      mapInstance.remove();
      mapRef.current = null;
    };
  }, [mapboxToken]);

  /* ── Re-center when incidentPoint changes ── */
  useEffect(() => {
    const map = mapRef.current;
    if (map && incidentPoint) {
      map.easeTo({
        center: [incidentPoint.longitude, incidentPoint.latitude],
        zoom: 13,
        duration: 1000,
      });
    }
  }, [incidentPoint?.latitude, incidentPoint?.longitude]);

  /* ── Sync Markers & Popups ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Clear old markers and popups
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    popupsRef.current.forEach((p) => p.remove());
    popupsRef.current = [];

    const userLat = incidentPoint?.latitude ?? 13.08;
    const userLon = incidentPoint?.longitude ?? 80.27;

    // Add YOUR LOCATION marker
    const youEl = document.createElement("div");
    youEl.innerHTML = `
      <div style="display:flex;align-items:center;gap:6px;background:#2563eb;color:#fff;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:700;font-family:Inter,sans-serif;box-shadow:0 2px 8px rgba(37,99,235,0.4);white-space:nowrap;">
        <span style="width:10px;height:10px;background:#fff;border-radius:50%;border:2px solid #2563eb;"></span>
        📍 You
      </div>
    `;
    const youMarker = new mapboxgl.Marker(youEl)
      .setLngLat([userLon, userLat])
      .addTo(map);
    markersRef.current.push(youMarker);

    // Add facility markers for each active layer
    LAYERS.filter((layer) => active[layer.key]).forEach((layer) => {
      data[layer.key].forEach((record) => {
        if (!record.point) return;
        const rLat = record.point.latitude;
        const rLon = record.point.longitude;

        // Calculate distance
        const distKm = (record as any).distance_km ?? Math.round(haversineDist(userLat, userLon, rLat, rLon) * 10) / 10;
        const travelMins = Math.round(distKm * 3.5); // ~17km/h average in disaster

        // Build detail text
        const detailParts: string[] = [];
        if (layer.key === "hospitals") {
          detailParts.push(`${record.available_beds ?? "?"} beds · ICU ${record.icu_available ?? "?"}`);
        } else if (layer.key === "shelters") {
          const spare = (record.capacity as number ?? 1000) - (record.current_occupancy as number ?? 200);
          detailParts.push(`${formatNumber(spare)} spots available`);
        } else if (layer.key === "police_fire") {
          detailParts.push((record as any).type === "fire" ? "🔥 Fire & Rescue" : "👮 Police Station");
        } else if (layer.key === "river_gauges") {
          const breached = (record.current_level_m as number) >= (record.warning_level_m as number);
          detailParts.push(`Water: ${record.current_level_m}m ${breached ? "⚠️ WARNING" : "✅ Normal"} (Danger: ${record.danger_level_m}m)`);
        }

        const name = String(record.name ?? record.station ?? "Facility");
        const shortName = name.length > 28 ? name.slice(0, 26) + "…" : name;

        // Create labeled pill marker
        const el = document.createElement("div");
        el.style.cursor = "pointer";
        el.innerHTML = `
          <div style="display:flex;align-items:center;gap:5px;background:${layer.color};color:#fff;padding:3px 8px;border-radius:16px;font-size:11px;font-weight:700;font-family:Inter,sans-serif;box-shadow:0 2px 6px ${layer.color}55;white-space:nowrap;max-width:200px;overflow:hidden;text-overflow:ellipsis;">
            <span style="font-size:13px;">${layer.emoji}</span>
            ${shortName}
          </div>
        `;

        // Build popup HTML
        const popupHTML = `
          <div style="font-family:Inter,system-ui,sans-serif;min-width:220px;max-width:280px;">
            <div style="font-size:14px;font-weight:800;color:#0f172a;margin-bottom:4px;">${name}</div>
            <div style="display:inline-block;background:${layer.color};color:#fff;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;margin-bottom:8px;">${layer.category}</div>
            <div style="font-size:12px;color:#475569;line-height:1.5;margin-bottom:8px;">
              ${detailParts.join("<br/>")}
              ${(record as any).address ? `<br/>📍 ${(record as any).address}` : ""}
              ${(record as any).contact ? `<br/>📞 ${(record as any).contact}` : ""}
            </div>
            <div style="display:flex;gap:6px;align-items:center;margin-bottom:4px;">
              <span style="font-size:12px;font-weight:700;color:#0f172a;">📏 ${distKm} km</span>
              <span style="font-size:11px;color:#64748b;">· ~${travelMins} min</span>
            </div>
            <a href="${googleMapsUrl(userLat, userLon, rLat, rLon)}" target="_blank" rel="noopener noreferrer"
               style="display:block;text-align:center;background:#2563eb;color:#fff;text-decoration:none;padding:8px 12px;border-radius:8px;font-size:12px;font-weight:700;margin-top:6px;">
              🧭 Navigate with Google Maps
            </a>
          </div>
        `;

        const popup = new mapboxgl.Popup({
          offset: 25,
          closeButton: true,
          closeOnClick: true,
          maxWidth: "300px",
        }).setHTML(popupHTML);

        const marker = new mapboxgl.Marker(el)
          .setLngLat([rLon, rLat])
          .setPopup(popup)
          .addTo(map);

        markersRef.current.push(marker);
        popupsRef.current.push(popup);
      });
    });

  }, [data, active, incidentPoint]);

  /* ── Render ── */
  return (
    <div className="relative h-full w-full overflow-hidden" style={{ background: "#f8fafc" }}>

      {/* Layer toggle bar */}
      <div
        style={{
          position: "absolute",
          top: 12,
          left: "50%",
          transform: "translateX(-50%)",
          zIndex: 20,
          display: "flex",
          flexWrap: "wrap",
          gap: 6,
          background: "rgba(255,255,255,0.95)",
          backdropFilter: "blur(12px)",
          padding: "6px 12px",
          borderRadius: 24,
          boxShadow: "0 2px 12px rgba(0,0,0,0.1)",
        }}
      >
        {LAYERS.map((layer) => (
          <button
            key={layer.key}
            onClick={() =>
              setActive((prev) => ({ ...prev, [layer.key]: !prev[layer.key] }))
            }
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              padding: "4px 10px",
              borderRadius: 16,
              border: active[layer.key] ? `2px solid ${layer.color}` : "2px solid #e2e8f0",
              background: active[layer.key] ? `${layer.color}15` : "#fff",
              color: active[layer.key] ? layer.color : "#94a3b8",
              fontSize: 11,
              fontWeight: 700,
              fontFamily: "Inter, system-ui, sans-serif",
              cursor: "pointer",
              transition: "all 0.15s ease",
              whiteSpace: "nowrap",
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: active[layer.key] ? layer.color : "#cbd5e1",
              }}
            />
            {layer.label}
            <span
              style={{
                background: active[layer.key] ? layer.color : "#e2e8f0",
                color: active[layer.key] ? "#fff" : "#94a3b8",
                fontSize: 9,
                fontWeight: 800,
                padding: "1px 5px",
                borderRadius: 8,
              }}
            >
              {data[layer.key].length}
            </span>
          </button>
        ))}
      </div>

      {/* Mapbox container */}
      {mapboxToken ? (
        <div ref={mapContainerRef} className="h-full w-full" />
      ) : (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            height: "100%",
            color: "#64748b",
            fontSize: 14,
            fontFamily: "Inter, sans-serif",
          }}
        >
          Map requires a Mapbox token. Please configure MAPBOX_TOKEN in backend settings.
        </div>
      )}
    </div>
  );
}
