import { useEffect, useMemo, useState, useRef } from "react";
import { formatNumber } from "../lib/format";
import { SEVERITY_COLOR } from "../lib/format";
import type {
  AgentRole,
  AllocationPlan,
  GeoPoint,
  RegistryRecord,
  SituationAssessment,
} from "../lib/types";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";

/**
 * Helper to generate a GeoJSON Polygon for a circle.
 * 1 degree of latitude is ~110.574 km.
 * 1 degree of longitude is ~111.32 * cos(latitude) km.
 */
function createGeoJSONCircle(center: [number, number], radiusInKm: number, points = 64) {
  const coords = {
    latitude: center[1],
    longitude: center[0]
  };
  const km = radiusInKm;
  const ret = [];
  const distanceX = km / (111.32 * Math.cos((coords.latitude * Math.PI) / 180));
  const distanceY = km / 110.574;
  for (let i = 0; i < points; i++) {
    const theta = (i / points) * (2 * Math.PI);
    const x = distanceX * Math.cos(theta);
    const y = distanceY * Math.sin(theta);
    ret.push([coords.longitude + x, coords.latitude + y]);
  }
  ret.push(ret[0]); // Close the polygon
  return {
    type: "Feature",
    geometry: {
      type: "Polygon",
      coordinates: [ret]
    },
    properties: {}
  };
}

type LayerKey = "hospitals" | "shelters" | "depots" | "river_gauges";

const LAYERS: { key: LayerKey; label: string; color: string; glyph: string }[] = [
  { key: "hospitals", label: "Hospitals", color: "#f87171", glyph: "H" },
  { key: "shelters", label: "Shelters", color: "#4ade80", glyph: "S" },
  { key: "depots", label: "Depots", color: "#818cf8", glyph: "D" },
  { key: "river_gauges", label: "Gauges", color: "#22d3ee", glyph: "G" },
];

const AGENT_TARGET_LAYERS: Partial<Record<AgentRole, LayerKey[]>> = {
  medical: ["hospitals"],
  shelter: ["shelters"],
  infrastructure: ["river_gauges", "depots"],
  allocation: ["depots"],
};

const WIDTH = 760;
const HEIGHT = 500;
const PADDING = 46;

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

interface Bounds {
  minLat: number;
  maxLat: number;
  minLon: number;
  maxLon: number;
}

export function TacticalMap({
  mapboxToken,
  incidentPoint,
  incidentName,
  assessment,
  allocationPlan,
  activeAgentRole,
  districtFacilities,
  liveHospitals,
}: Props) {
  const [data, setData] = useState<Record<LayerKey, RegistryRecord[]>>({
    hospitals: [],
    shelters: [],
    depots: [],
    river_gauges: [],
  });

  useEffect(() => {
    // Prioritize live hospitals fetched from OpenStreetMap Healthcare API!
    const hospSource = liveHospitals && liveHospitals.length > 0
      ? liveHospitals
      : districtFacilities?.hospitals || [];

    const nextHospitals = hospSource.map((h: any) => ({
      name: h.name,
      point: { latitude: h.lat, longitude: h.lon },
      available_beds: h.available_beds ?? h.icu_available ?? 10,
      icu_available: h.icu_available ?? 4,
    }));

    const nextShelters = (districtFacilities?.shelters || []).map((s: any) => ({
      name: s.name,
      point: {
        latitude: s.lat ?? (incidentPoint?.latitude ? incidentPoint.latitude + 0.01 : 26.15),
        longitude: s.lon ?? (incidentPoint?.longitude ? incidentPoint.longitude + 0.01 : 91.74),
      },
      capacity: s.capacity ?? 1000,
      current_occupancy: s.current_occupancy ?? 200,
      flood_safe: true,
    }));

    const nextDepots = (districtFacilities?.police_fire || []).map((pf: any) => ({
      name: pf.name,
      point: {
        latitude: incidentPoint?.latitude ? incidentPoint.latitude - 0.012 : 26.13,
        longitude: incidentPoint?.longitude ? incidentPoint.longitude - 0.012 : 91.72,
      },
      organization: pf.name,
    }));

    setData({
      hospitals: nextHospitals,
      shelters: nextShelters,
      depots: nextDepots,
      river_gauges: [],
    });
  }, [districtFacilities, liveHospitals, incidentPoint]);
  const [active, setActive] = useState<Record<LayerKey, boolean>>({
    hospitals: true,
    shelters: true,
    depots: true,
    river_gauges: true,
  });
  const [hovered, setHovered] = useState<{
    x: number;
    y: number;
    label: string;
    detail: string;
  } | null>(null);

  // Mapbox GL JS references
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<mapboxgl.Map | null>(null);
  const markersRef = useRef<mapboxgl.Marker[]>([]);



  // Compute Bounds (used for SVG projection as fallback)
  const bounds: Bounds = useMemo(() => {
    const points: GeoPoint[] = [];
    for (const layer of LAYERS) {
      for (const record of data[layer.key]) {
        if (record.point) points.push(record.point);
      }
    }
    if (incidentPoint) points.push(incidentPoint);

    if (points.length === 0) {
      return { minLat: 9.3, maxLat: 10.6, minLon: 76.1, maxLon: 76.7 };
    }

    const lats = points.map((p) => p.latitude);
    const lons = points.map((p) => p.longitude);
    const pad = 0.06;
    return {
      minLat: Math.min(...lats) - pad,
      maxLat: Math.max(...lats) + pad,
      minLon: Math.min(...lons) - pad,
      maxLon: Math.max(...lons) + pad,
    };
  }, [data, incidentPoint]);

  /** Equirectangular projection, corrected for longitude convergence. */
  const project = useMemo(() => {
    const latSpan = bounds.maxLat - bounds.minLat || 1;
    const lonSpan = bounds.maxLon - bounds.minLon || 1;
    return (point: GeoPoint) => ({
      x:
        PADDING +
        ((point.longitude - bounds.minLon) / lonSpan) * (WIDTH - PADDING * 2),
      y:
        PADDING +
        ((bounds.maxLat - point.latitude) / latSpan) * (HEIGHT - PADDING * 2),
    });
  }, [bounds]);

  /** Convert a radius in km into projected pixels (latitude is uniform). */
  const kmToPixels = useMemo(() => {
    const latSpan = bounds.maxLat - bounds.minLat || 1;
    const pixelsPerDegreeLat = (HEIGHT - PADDING * 2) / latSpan;
    return (km: number) => (km / 111.32) * pixelsPerDegreeLat;
  }, [bounds]);

  const incidentXY = incidentPoint ? project(incidentPoint) : null;
  const severity = assessment?.severity ?? "informational";
  const severityColor = SEVERITY_COLOR[severity];

  const supplyLines = useMemo(() => {
    if (!allocationPlan || !incidentXY) return [];
    const seen = new Set<string>();
    const lines: { x: number; y: number; label: string; units: number }[] = [];

    for (const allocation of allocationPlan.allocations) {
      if (seen.has(allocation.from_depot_name)) continue;
      const depot = data.depots.find(
        (d) => d.name === allocation.from_depot_name,
      );
      if (!depot?.point) continue;
      seen.add(allocation.from_depot_name);
      const xy = project(depot.point);
      lines.push({
        ...xy,
        label: allocation.from_depot_name,
        units: allocationPlan.allocations
          .filter((a) => a.from_depot_name === allocation.from_depot_name)
          .reduce((total, a) => total + a.quantity, 0),
      });
    }
    return lines;
  }, [allocationPlan, data.depots, project, incidentXY]);

  // GPS Supply lines for Mapbox GL JS
  const supplyLinesGPS = useMemo(() => {
    if (!allocationPlan || !incidentPoint) return [];
    const seen = new Set<string>();
    const lines: { lon: number; lat: number; label: string; units: number }[] = [];

    for (const allocation of allocationPlan.allocations) {
      if (seen.has(allocation.from_depot_name)) continue;
      const depot = data.depots.find(
        (d) => d.name === allocation.from_depot_name,
      );
      if (!depot?.point) continue;
      seen.add(allocation.from_depot_name);
      lines.push({
        lon: depot.point.longitude,
        lat: depot.point.latitude,
        label: allocation.from_depot_name,
        units: allocationPlan.allocations
          .filter((a) => a.from_depot_name === allocation.from_depot_name)
          .reduce((total, a) => total + a.quantity, 0),
      });
    }
    return lines;
  }, [allocationPlan, data.depots, incidentPoint]);

  // Mapbox GL JS Initialization
  useEffect(() => {
    if (!mapboxToken || !mapContainerRef.current) return;

    mapboxgl.accessToken = mapboxToken;
    const defaultCenter: [number, number] = incidentPoint
      ? [incidentPoint.longitude, incidentPoint.latitude]
      : [76.4, 9.9];

    const mapInstance = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: "mapbox://styles/mapbox/dark-v11",
      center: defaultCenter,
      zoom: incidentPoint ? 10 : 8.5,
      attributionControl: false,
    });

    mapInstance.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "bottom-right");

    mapInstance.on("load", () => {
      setMap(mapInstance);
    });

    mapInstance.on("move", () => {
      setHovered(null);
    });

    return () => {
      mapInstance.remove();
      setMap(null);
    };
  }, [mapboxToken]);

  // Center camera smoothly whenever incidentPoint coordinates change
  useEffect(() => {
    if (map && incidentPoint) {
      map.easeTo({
        center: [incidentPoint.longitude, incidentPoint.latitude],
        zoom: 11.5,
        duration: 1200,
      });
    }
  }, [map, incidentPoint?.latitude, incidentPoint?.longitude]);

  // Sync Mapbox markers, hazard boundary circle, and routing lines
  useEffect(() => {
    if (!map) return;

    // 1. Clear existing markers
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];

    // 2. Add asset markers
    const targetLayers = activeAgentRole ? AGENT_TARGET_LAYERS[activeAgentRole] ?? [] : null;

    LAYERS.filter((layer) => active[layer.key]).forEach((layer) => {
      const isTargeted = targetLayers ? targetLayers.includes(layer.key) : true;

      data[layer.key].forEach((record) => {
        if (!record.point) return;

        const breached =
          layer.key === "river_gauges" &&
          typeof record.current_level_m === "number" &&
          typeof record.danger_level_m === "number" &&
          (record.current_level_m as number) >=
            (record.warning_level_m as number);
        const unsafe =
          layer.key === "shelters" && record.flood_safe === false;

        const detail =
          layer.key === "hospitals"
            ? `${record.available_beds} beds free · ICU ${record.icu_available}`
            : layer.key === "shelters"
              ? `${formatNumber(
                  (record.capacity as number) -
                    (record.current_occupancy as number),
                )} spare${unsafe ? " · FLOOD-EXPOSED" : ""}`
              : layer.key === "depots"
                ? String(record.organization ?? "")
                : `${record.current_level_m}m / danger ${record.danger_level_m}m`;

        // Create Custom HTML element
        const el = document.createElement("div");
        el.className = "relative cursor-crosshair transition-all duration-200 hover:scale-125";
        el.style.opacity = isTargeted ? "1" : "0.2";
        
        const dot = document.createElement("div");
        dot.style.width = isTargeted && targetLayers ? "12px" : "8px";
        dot.style.height = isTargeted && targetLayers ? "12px" : "8px";
        dot.style.backgroundColor = breached || unsafe ? "#ef4444" : layer.color;
        dot.style.boxShadow = isTargeted && targetLayers ? `0 0 10px ${layer.color}` : "none";
        
        if (layer.key === "depots") {
          dot.style.transform = "rotate(45deg)";
        } else {
          dot.style.borderRadius = "50%";
        }
        el.appendChild(dot);

        if (breached || unsafe || (isTargeted && targetLayers)) {
          const pulse = document.createElement("div");
          pulse.className = "absolute -inset-1.5 rounded-full border border-current animate-ping opacity-75";
          pulse.style.color = breached || unsafe ? "#ef4444" : layer.color;
          el.appendChild(pulse);
        }

        el.addEventListener("mouseenter", () => {
          const pt = map.project([record.point.longitude, record.point.latitude]);
          setHovered({
            x: pt.x,
            y: pt.y,
            label: String(record.name ?? record.station ?? ""),
            detail,
          });
        });
        el.addEventListener("mouseleave", () => setHovered(null));

        const m = new mapboxgl.Marker(el)
          .setLngLat([record.point.longitude, record.point.latitude])
          .addTo(map);
        markersRef.current.push(m);
      });
    });

    // 3. Add incident marker
    if (incidentPoint) {
      const el = document.createElement("div");
      el.className = "relative flex items-center justify-center";
      
      const dot = document.createElement("div");
      dot.style.width = "12px";
      dot.style.height = "12px";
      dot.style.backgroundColor = severityColor;
      dot.style.borderRadius = "50%";
      el.appendChild(dot);

      const pulse = document.createElement("div");
      pulse.className = "absolute rounded-full border border-current animate-ping";
      pulse.style.color = severityColor;
      pulse.style.width = "26px";
      pulse.style.height = "26px";
      el.appendChild(pulse);

      if (incidentName) {
        const label = document.createElement("div");
        label.className = "absolute left-5 font-mono text-[10.5px] font-semibold whitespace-nowrap bg-void/80 px-1.5 py-0.5 rounded border border-edge/60 shadow-md";
        label.style.color = severityColor;
        label.innerText = incidentName;
        el.appendChild(label);
      }

      const m = new mapboxgl.Marker(el)
        .setLngLat([incidentPoint.longitude, incidentPoint.latitude])
        .addTo(map);
      markersRef.current.push(m);
    }

    // 4. Update GeoJSON sources/layers for hazard zone & lines
    const isWeatherTarget = activeAgentRole === "weather";
    const isAllocationTarget = activeAgentRole === "allocation";

    if (!map.getSource("hazard-source")) {
      map.addSource("hazard-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      map.addLayer({
        id: "hazard-layer-fill",
        type: "fill",
        source: "hazard-source",
        paint: {
          "fill-color": severityColor,
          "fill-opacity": isWeatherTarget ? 0.35 : 0.14,
        }
      });
      map.addLayer({
        id: "hazard-layer-outline",
        type: "line",
        source: "hazard-source",
        paint: {
          "line-color": severityColor,
          "line-width": isWeatherTarget ? 3 : 1.5,
          "line-dasharray": [4, 3],
        }
      });
    } else {
      map.setPaintProperty("hazard-layer-fill", "fill-color", severityColor);
      map.setPaintProperty("hazard-layer-fill", "fill-opacity", isWeatherTarget ? 0.35 : 0.14);
      map.setPaintProperty("hazard-layer-outline", "line-color", severityColor);
      map.setPaintProperty("hazard-layer-outline", "line-width", isWeatherTarget ? 3 : 1.5);
    }

    const hazardSource = map.getSource("hazard-source") as mapboxgl.GeoJSONSource;
    if (hazardSource) {
      if (incidentPoint && assessment) {
        const circleGeoJSON = createGeoJSONCircle(
          [incidentPoint.longitude, incidentPoint.latitude],
          assessment.impact.affected_radius_km
        );
        hazardSource.setData(circleGeoJSON as any);
      } else {
        hazardSource.setData({ type: "FeatureCollection", features: [] });
      }
    }

    if (!map.getSource("lines-source")) {
      map.addSource("lines-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      map.addLayer({
        id: "lines-layer",
        type: "line",
        source: "lines-source",
        paint: {
          "line-color": "#818cf8",
          "line-width": isAllocationTarget ? 3.5 : 1.8,
          "line-opacity": isAllocationTarget ? 0.95 : 0.7,
          "line-dasharray": [3, 2],
        }
      });
    } else {
      map.setPaintProperty("lines-layer", "line-width", isAllocationTarget ? 3.5 : 1.8);
      map.setPaintProperty("lines-layer", "line-opacity", isAllocationTarget ? 0.95 : 0.7);
    }

    const linesSource = map.getSource("lines-source") as mapboxgl.GeoJSONSource;
    if (linesSource && incidentPoint) {
      const features = supplyLinesGPS.map((line) => ({
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: [
            [line.lon, line.lat],
            [incidentPoint.longitude, incidentPoint.latitude]
          ]
        },
        properties: {}
      }));
      linesSource.setData({
        type: "FeatureCollection",
        features
      } as any);
    }

  }, [map, data, active, incidentPoint, assessment, supplyLinesGPS, severityColor, activeAgentRole]);

  // Adjust zoom bounds dynamically to fit elements
  useEffect(() => {
    if (!map) return;

    const points: [number, number][] = [];
    if (incidentPoint) {
      points.push([incidentPoint.longitude, incidentPoint.latitude]);
    }
    LAYERS.filter((l) => active[l.key]).forEach((layer) => {
      data[layer.key].forEach((record) => {
        if (record.point) {
          points.push([record.point.longitude, record.point.latitude]);
        }
      });
    });

    if (points.length > 0) {
      const startBounds = new mapboxgl.LngLatBounds(points[0], points[0]);
      points.forEach((p) => startBounds.extend(p));
      map.fitBounds(startBounds, { padding: 60, maxZoom: 12, duration: 1200 });
    }
  }, [map, data, active, incidentPoint]);

  return (
    <div className="relative h-full w-full overflow-hidden bg-abyss">
      {/* Centered Layer Controls — perfectly positioned in center top to avoid drawer collisions */}
      <div className="absolute top-12 left-1/2 -translate-x-1/2 z-20 flex flex-wrap items-center gap-1.5 rounded-full border border-edge-bright/80 bg-abyss/95 px-3 py-1 backdrop-blur-md shadow-2xl pointer-events-auto transition-all">
        <span className="font-mono text-[9px] font-bold text-ink-faint tracking-widest uppercase mr-1 hidden sm:inline">
          LAYERS:
        </span>
        {LAYERS.map((layer) => (
          <button
            key={layer.key}
            onClick={() =>
              setActive((previous) => ({
                ...previous,
                [layer.key]: !previous[layer.key],
              }))
            }
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[9.5px] font-semibold transition-all ${
              active[layer.key]
                ? "border-edge-bright bg-panel-raised text-ink shadow-sm"
                : "border-edge/50 bg-transparent text-ink-faint opacity-50 hover:opacity-100"
            }`}
          >
            <span
              className="size-1.5 rounded-full"
              style={{
                background: active[layer.key] ? layer.color : "#31466e",
                boxShadow: active[layer.key] ? `0 0 6px ${layer.color}` : "none",
              }}
            />
            {layer.label}
            <span className="rounded-full bg-abyss px-1 font-extrabold text-[8.5px] text-ink-dim">
              {data[layer.key].length}
            </span>
          </button>
        ))}
      </div>

      <div className="absolute bottom-3 left-3 z-10 font-mono text-[9px] tracking-wide text-ink-faint rounded bg-abyss/80 border border-edge/40 px-2 py-0.5 backdrop-blur-sm">
        {mapboxToken ? "MAPBOX GL JS · VECTOR TILES" : "TACTICAL EQUIRECTANGULAR ENGINE"}
      </div>


      {/* Map Content Render */}
      {mapboxToken ? (
        <>
          <div ref={mapContainerRef} className="h-full w-full" />
          
          {/* React HTML Tooltip Overlay for Mapbox */}
          {hovered && (
            <div
              className="absolute z-20 pointer-events-none rounded border border-edge-bright bg-panel px-2.5 py-1.5 font-mono shadow-md"
              style={{
                left: `${Math.min(hovered.x + 10, (mapContainerRef.current?.clientWidth || WIDTH) - 230)}px`,
                top: `${hovered.y - 45}px`,
                width: "220px",
              }}
            >
              <div className="text-[9.5px] font-semibold text-ink truncate">{hovered.label}</div>
              <div className="text-[8.5px] text-ink-dim truncate">{hovered.detail}</div>
            </div>
          )}
        </>
      ) : (
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="grid-field h-full w-full"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <radialGradient id="hazard-fill">
              <stop offset="0%" stopColor={severityColor} stopOpacity="0.22" />
              <stop offset="70%" stopColor={severityColor} stopOpacity="0.07" />
              <stop offset="100%" stopColor={severityColor} stopOpacity="0" />
            </radialGradient>
          </defs>

          {/* Supply corridors, drawn beneath every asset marker */}
          {incidentXY &&
            supplyLines.map((line) => (
              <g key={line.label}>
                <line
                  x1={line.x}
                  y1={line.y}
                  x2={incidentXY.x}
                  y2={incidentXY.y}
                  stroke="#818cf8"
                  strokeWidth="1"
                  opacity="0.5"
                  className="flow-line"
                />
              </g>
            ))}

          {/* Hazard radius */}
          {incidentXY && assessment && (
            <>
              <circle
                cx={incidentXY.x}
                cy={incidentXY.y}
                r={kmToPixels(assessment.impact.affected_radius_km)}
                fill="url(#hazard-fill)"
                stroke={severityColor}
                strokeWidth="1"
                strokeDasharray="4 3"
                opacity="0.8"
              />
              <text
                x={incidentXY.x}
                y={incidentXY.y - kmToPixels(assessment.impact.affected_radius_km) - 6}
                textAnchor="middle"
                fontSize="9"
                fontFamily="var(--font-mono)"
                fill={severityColor}
              >
                {assessment.impact.affected_radius_km} km
              </text>
            </>
          )}

          {/* Asset markers */}
          {LAYERS.filter((layer) => active[layer.key]).map((layer) =>
            data[layer.key].map((record, index) => {
              if (!record.point) return null;
              const xy = project(record.point);
              const breached =
                layer.key === "river_gauges" &&
                typeof record.current_level_m === "number" &&
                typeof record.danger_level_m === "number" &&
                (record.current_level_m as number) >=
                  (record.warning_level_m as number);
              const unsafe =
                layer.key === "shelters" && record.flood_safe === false;

              const detail =
                layer.key === "hospitals"
                  ? `${record.available_beds} beds free · ICU ${record.icu_available}`
                  : layer.key === "shelters"
                    ? `${formatNumber(
                        (record.capacity as number) -
                          (record.current_occupancy as number),
                      )} spare${unsafe ? " · FLOOD-EXPOSED" : ""}`
                    : layer.key === "depots"
                      ? String(record.organization ?? "")
                      : `${record.current_level_m}m / danger ${record.danger_level_m}m`;

              return (
                <g
                  key={`${layer.key}-${index}`}
                  onMouseEnter={() =>
                    setHovered({
                      x: xy.x,
                      y: xy.y,
                      label: String(record.name ?? record.station ?? ""),
                      detail,
                    })
                  }
                  onMouseLeave={() => setHovered(null)}
                  className="cursor-crosshair"
                >
                  <rect
                    x={xy.x - 4}
                    y={xy.y - 4}
                    width="8"
                    height="8"
                    fill={breached || unsafe ? "#ef4444" : layer.color}
                    opacity={breached || unsafe ? 1 : 0.85}
                    transform={
                      layer.key === "depots" ? `rotate(45 ${xy.x} ${xy.y})` : undefined
                    }
                  />
                  {(breached || unsafe) && (
                    <circle
                      cx={xy.x}
                      cy={xy.y}
                      r="9"
                      fill="none"
                      stroke="#ef4444"
                      strokeWidth="1"
                      opacity="0.6"
                    >
                      <animate
                        attributeName="r"
                        values="6;12;6"
                        dur="2s"
                        repeatCount="indefinite"
                      />
                      <animate
                        attributeName="opacity"
                        values="0.7;0;0.7"
                        dur="2s"
                        repeatCount="indefinite"
                      />
                    </circle>
                  )}
                </g>
              );
            }),
          )}

          {/* Incident marker */}
          {incidentXY && (
            <g>
              <circle
                cx={incidentXY.x}
                cy={incidentXY.y}
                r="7"
                fill={severityColor}
              />
              <circle
                cx={incidentXY.x}
                cy={incidentXY.y}
                r="12"
                fill="none"
                stroke={severityColor}
                strokeWidth="1.5"
              >
                <animate
                  attributeName="r"
                  values="9;20;9"
                  dur="2.4s"
                  repeatCount="indefinite"
                />
                <animate
                  attributeName="opacity"
                  values="0.9;0;0.9"
                  dur="2.4s"
                  repeatCount="indefinite"
                />
              </circle>
              <text
                x={incidentXY.x + 14}
                y={incidentXY.y + 4}
                fontSize="11"
                fontFamily="var(--font-mono)"
                fontWeight="600"
                fill={severityColor}
              >
                {incidentName}
              </text>
            </g>
          )}

          {/* Hover readout */}
          {hovered && (
            <g pointerEvents="none">
              <rect
                x={Math.min(hovered.x + 10, WIDTH - 230)}
                y={hovered.y - 30}
                width="220"
                height="34"
                rx="3"
                fill="#0c1120"
                stroke="#2a3752"
              />
              <text
                x={Math.min(hovered.x + 16, WIDTH - 224)}
                y={hovered.y - 17}
                fontSize="9.5"
                fontFamily="var(--font-mono)"
                fill="#e8edf7"
              >
                {hovered.label.slice(0, 34)}
              </text>
              <text
                x={Math.min(hovered.x + 16, WIDTH - 224)}
                y={hovered.y - 6}
                fontSize="8.5"
                fontFamily="var(--font-mono)"
                fill="#94a3bd"
              >
                {hovered.detail.slice(0, 40)}
              </text>
            </g>
          )}
        </svg>
      )}
    </div>
  );
}

