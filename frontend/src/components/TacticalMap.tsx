import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { formatNumber } from "../lib/format";
import { SEVERITY_COLOR } from "../lib/format";
import type {
  AllocationPlan,
  GeoPoint,
  RegistryRecord,
  SituationAssessment,
} from "../lib/types";

/**
 * Tactical situation display.
 *
 * Rendered as a self-contained SVG with an equirectangular projection rather
 * than a tile-based map. Three reasons, in order of importance:
 *
 *  1. It works with no network and no map-provider API key, so a demo cannot
 *     fail because conference wifi is saturated.
 *  2. Basemap tiles are visual noise here — the decision-relevant information
 *     is the relative geometry of assets, hazard radius and supply lines, all
 *     of which read better against an empty field.
 *  3. It keeps the whole app dependency-free at the render layer.
 */

type LayerKey = "hospitals" | "shelters" | "depots" | "river_gauges";

const LAYERS: { key: LayerKey; label: string; color: string; glyph: string }[] = [
  { key: "hospitals", label: "Hospitals", color: "#f87171", glyph: "H" },
  { key: "shelters", label: "Shelters", color: "#4ade80", glyph: "S" },
  { key: "depots", label: "Depots", color: "#818cf8", glyph: "D" },
  { key: "river_gauges", label: "Gauges", color: "#22d3ee", glyph: "G" },
];

const WIDTH = 760;
const HEIGHT = 500;
const PADDING = 46;

interface Props {
  incidentPoint?: GeoPoint | null;
  incidentName?: string;
  assessment?: SituationAssessment | null;
  allocationPlan?: AllocationPlan | null;
}

interface Bounds {
  minLat: number;
  maxLat: number;
  minLon: number;
  maxLon: number;
}

export function TacticalMap({
  incidentPoint,
  incidentName,
  assessment,
  allocationPlan,
}: Props) {
  const [data, setData] = useState<Record<LayerKey, RegistryRecord[]>>({
    hospitals: [],
    shelters: [],
    depots: [],
    river_gauges: [],
  });
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

  useEffect(() => {
    let cancelled = false;
    Promise.all(LAYERS.map((layer) => api.registry(layer.key)))
      .then((responses) => {
        if (cancelled) return;
        const next = {} as Record<LayerKey, RegistryRecord[]>;
        responses.forEach((response, index) => {
          next[LAYERS[index].key] = response.records as RegistryRecord[];
        });
        setData(next);
      })
      .catch(() => {
        /* map degrades to the incident marker alone */
      });
    return () => {
      cancelled = true;
    };
  }, []);

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

  return (
    <div className="relative h-full overflow-hidden rounded border border-edge bg-abyss">
      <div className="absolute left-2 top-2 z-10 flex flex-wrap gap-1">
        {LAYERS.map((layer) => (
          <button
            key={layer.key}
            onClick={() =>
              setActive((previous) => ({
                ...previous,
                [layer.key]: !previous[layer.key],
              }))
            }
            className={`flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[9px] transition-colors ${
              active[layer.key]
                ? "border-edge-bright bg-panel text-ink"
                : "border-edge bg-transparent text-ink-faint"
            }`}
          >
            <span
              className="size-1.5 rounded-full"
              style={{
                background: active[layer.key] ? layer.color : "#2a3752",
              }}
            />
            {layer.label}
            <span className="text-ink-faint">{data[layer.key].length}</span>
          </button>
        ))}
      </div>

      <div className="absolute bottom-2 left-2 z-10 font-mono text-[8px] text-ink-faint">
        EQUIRECTANGULAR · SYNTHETIC ASSET REGISTRY
      </div>

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
    </div>
  );
}
