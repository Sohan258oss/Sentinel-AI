import { TacticalMap } from "./TacticalMap";
import type { AllocationPlan, GeoPoint, SituationAssessment } from "../lib/types";

interface Props {
  mapboxToken?: string | null;
  incidentPoint?: GeoPoint | null;
  incidentName?: string;
  assessment?: SituationAssessment | null;
  allocationPlan?: AllocationPlan | null;
  districtFacilities?: any;
  liveHospitals?: any[];
}

export function MapPage({
  mapboxToken,
  incidentPoint,
  incidentName,
  assessment,
  allocationPlan,
  districtFacilities,
  liveHospitals,
}: Props) {
  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
      }}
    >
      <TacticalMap
        mapboxToken={mapboxToken}
        incidentPoint={incidentPoint}
        incidentName={incidentName}
        assessment={assessment}
        allocationPlan={allocationPlan}
        activeAgentRole={null}
        districtFacilities={districtFacilities}
        liveHospitals={liveHospitals}
      />

      {/* Clean legend overlay */}
      <div
        style={{
          position: "absolute",
          bottom: 16,
          left: 16,
          background: "rgba(255,255,255,0.95)",
          backdropFilter: "blur(12px)",
          borderRadius: 12,
          padding: "10px 14px",
          boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
          display: "flex",
          flexDirection: "column",
          gap: 6,
          fontSize: 11,
          fontWeight: 600,
          zIndex: 10,
        }}
      >
        {[
          { color: "#2563EB", label: "📍 Your Location" },
          { color: "#dc2626", label: "🏥 Hospitals" },
          { color: "#059669", label: "⛺ Relief Shelters" },
          { color: "#d97706", label: "🚔 Police & Fire" },
          { color: "#0891b2", label: "🌊 Flood Monitoring" },
        ].map((item) => (
          <div key={item.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span
              style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: item.color,
                flexShrink: 0,
              }}
            />
            <span style={{ color: "#334155" }}>{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
