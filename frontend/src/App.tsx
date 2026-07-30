/**
 * App — SentinelAI Emergency Companion.
 *
 * Minimal 5-tab mobile-first layout:
 *   🏠 Home  |  🗺 Map  |  🤖 AI  |  🚨 Alerts  |  ⚙ More
 *
 * The entire backend integration (multi-agent SSE, district intelligence,
 * GPS resolution) is preserved from the original. Only the presentation
 * layer has been redesigned to feel like Apple/Google Maps/Uber.
 */
import { useEffect, useState } from "react";
import { LocationModal } from "./components/LocationModal";
import { BottomNav, type TabKey } from "./components/BottomNav";
import { TopBar } from "./components/TopBar";
import { HomePage } from "./components/HomePage";
import { MapPage } from "./components/MapPage";
import { CitizenAssistantChat } from "./components/CitizenAssistantChat";
import { AlertsPage } from "./components/AlertsPage";
import { MorePage } from "./components/MorePage";
import { useIncidentRun } from "./hooks/useIncidentRun";
import { api } from "./lib/api";
import type { SystemStatus } from "./lib/types";

export default function App() {
  const run = useIncidentRun();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("home");
  const [districtIntelligenceData, setDistrictIntelligenceData] = useState<any>(null);
  const [liveHospitals] = useState<any[]>([]);
  const [isLocationModalOpen, setIsLocationModalOpen] = useState(false);

  const [userCoords, setUserCoords] = useState<{ lat: number; lon: number }>({
    lat: 26.1445,
    lon: 91.7362,
  });

  const [currentLocation, setCurrentLocation] = useState<{
    state: string;
    district: string;
    hazard: string;
  }>({ state: "Assam", district: "Kamrup Metropolitan", hazard: "flood" });

  // Fetch system status on mount
  useEffect(() => {
    api.systemStatus().then(setStatus).catch(() => setStatus(null));
    api
      .districtIntelligence(currentLocation.state, currentLocation.district, currentLocation.hazard)
      .then((data) => {
        setDistrictIntelligenceData(data);
        if (data?.district_info?.lat && data?.district_info?.lon) {
          setUserCoords({ lat: data.district_info.lat, lon: data.district_info.lon });
        }
      })
      .catch(() => setDistrictIntelligenceData(null));
  }, []);

  // Refresh district intelligence when location changes
  const refreshDistrictIntelligence = (state: string, district: string, hazard: string) => {
    api
      .districtIntelligence(state, district, hazard)
      .then((data) => {
        setDistrictIntelligenceData(data);
        if (data?.district_info?.lat && data?.district_info?.lon) {
          setUserCoords({ lat: data.district_info.lat, lon: data.district_info.lon });
        }
      })
      .catch(() => setDistrictIntelligenceData(null));
  };

  const handleLocationResolved = (state: string, district: string, lat: number, lon: number) => {
    if (lat && lon) setUserCoords({ lat, lon });
    setCurrentLocation((prev) => ({ ...prev, state, district }));
    refreshDistrictIntelligence(state, district, currentLocation.hazard);
  };

  const handleTriggerEmergency = (
    disasterKey: string,
    districtName: string,
    stateName: string,
    lat: number,
    lon: number
  ) => {
    setCurrentLocation({ state: stateName, district: districtName, hazard: disasterKey });
    refreshDistrictIntelligence(stateName, districtName, disasterKey);

    void run.startCustom({
      description: `🚨 EMERGENCY: ${disasterKey.toUpperCase()} in ${districtName}, ${stateName}. Citizen requires immediate multi-agent assistance, safe shelter route, and medical evacuation guidance.`,
      location_name: districtName,
      district: districtName,
      state: stateName,
      latitude: lat,
      longitude: lon,
      population: 750000,
      declared_hazard: disasterKey,
      reported_casualties: 0,
      channel: "emergency_button",
      verified: true,
    });
  };

  const handleLocationChange = (state: string, district: string, hazard: string) => {
    setCurrentLocation({ state, district, hazard });
    refreshDistrictIntelligence(state, district, hazard);
  };

  const picture = run.picture;
  const report = picture?.report;

  const incidentPoint =
    report?.location.point ?? {
      latitude: userCoords.lat,
      longitude: userCoords.lon,
    };

  return (
    <div className="app-shell">
      {/* ── Minimal Top Bar ── */}
      <TopBar
        district={currentLocation.district}
        state={currentLocation.state}
        running={run.running}
        onOpenLocationModal={() => setIsLocationModalOpen(true)}
      />

      {/* ── Page Content ── */}
      {activeTab === "home" && (
        <HomePage
          currentLocation={currentLocation}
          districtIntelligenceData={districtIntelligenceData}
          onTriggerEmergency={handleTriggerEmergency}
          onLocationResolved={handleLocationResolved}
          onOpenLocationModal={() => setIsLocationModalOpen(true)}
          running={run.running}
          picture={picture}
        />
      )}

      {activeTab === "map" && (
        <MapPage
          mapboxToken={status?.mapbox_token}
          incidentPoint={incidentPoint}
          incidentName={report?.location.name ?? currentLocation.district}
          assessment={picture?.assessment ?? null}
          allocationPlan={picture?.allocation_plan ?? null}
          districtFacilities={districtIntelligenceData?.facilities}
          liveHospitals={liveHospitals}
        />
      )}

      {activeTab === "assistant" && (
        <div className="page-content" style={{ background: "var(--color-bg)" }}>
          <CitizenAssistantChat
            selectedDistrict={currentLocation.district}
            selectedState={currentLocation.state}
            selectedHazard={currentLocation.hazard}
          />
        </div>
      )}

      {activeTab === "alerts" && (
        <AlertsPage
          traces={run.traces}
          running={run.running}
          picture={picture}
          currentLocation={currentLocation}
        />
      )}

      {activeTab === "more" && (
        <MorePage
          currentLocation={currentLocation}
          onLocationChange={handleLocationChange}
          traces={run.traces}
          agents={run.agents}
          running={run.running}
          status={status}
          picture={picture}
        />
      )}

      {/* ── Location Modal ── */}
      <LocationModal
        isOpen={isLocationModalOpen}
        onClose={() => setIsLocationModalOpen(false)}
        currentLocation={currentLocation}
        onSelectLocation={handleLocationResolved}
      />

      {/* ── Bottom Navigation ── */}
      <BottomNav activeTab={activeTab} onTabChange={setActiveTab} />
    </div>
  );
}
