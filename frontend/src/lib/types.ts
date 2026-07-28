/**
 * Mirrors the backend Pydantic contracts.
 *
 * Only the fields the UI actually renders are modelled. Deliberately narrower
 * than the server schema — a UI type that tracks every backend field becomes a
 * maintenance tax without buying any safety at the render layer.
 */

export type Severity =
  | "informational"
  | "minor"
  | "moderate"
  | "severe"
  | "catastrophic";

export type AgentRole =
  | "intake"
  | "situation_analysis"
  | "commander"
  | "weather"
  | "infrastructure"
  | "medical"
  | "shelter"
  | "knowledge"
  | "logistics"
  | "volunteer"
  | "allocation"
  | "reflection"
  | "communication";

export type AgentStatus =
  | "idle"
  | "dispatched"
  | "running"
  | "completed"
  | "degraded"
  | "failed"
  | "skipped";

export type TraceEventType =
  | "node_started"
  | "node_completed"
  | "node_failed"
  | "reasoning"
  | "tool_call"
  | "tool_result"
  | "retrieval"
  | "routing_decision"
  | "critique"
  | "revision"
  | "run_started"
  | "run_completed"
  | "error";

export interface ToolInvocation {
  tool_name: string;
  result_preview: string;
  succeeded: boolean;
  used_fallback: boolean;
  latency_ms: number;
}

export interface AgentTrace {
  event_id: string;
  incident_id: string;
  run_id: string;
  sequence: number;
  timestamp: string;
  event_type: TraceEventType;
  agent: AgentRole;
  status: AgentStatus;
  title: string;
  detail: string;
  tool_invocation?: ToolInvocation | null;
  confidence?: number | null;
  latency_ms?: number | null;
  payload: Record<string, unknown>;
}

export interface GeoPoint {
  latitude: number;
  longitude: number;
}

export interface LocationRef {
  name: string;
  point: GeoPoint;
  district?: string | null;
  state?: string | null;
  population?: number | null;
}

export interface Citation {
  source_id: string;
  document_title: string;
  section?: string | null;
  snippet: string;
  relevance: number;
  authority?: string | null;
}

export interface Recommendation {
  action: string;
  rationale: string;
  urgency: "immediate" | "urgent" | "routine";
  owner: string;
}

export interface Measure {
  label: string;
  value: number;
  unit: string;
}

export interface IntelligenceProduct {
  agent: AgentRole;
  headline: string;
  confidence: number;
  key_findings: string[];
  recommendations: Recommendation[];
  citations: Citation[];
  metrics: Measure[];
  degraded: boolean;
}

export interface HospitalStatus {
  facility_id: string;
  name: string;
  point: GeoPoint;
  distance_km: number;
  total_beds: number;
  available_beds: number;
  icu_available: number;
  trauma_capable: boolean;
  blood_bank: boolean;
  operational_status: string;
}

export interface ShelterSite {
  shelter_id: string;
  name: string;
  point: GeoPoint;
  distance_km: number;
  capacity: number;
  current_occupancy: number;
  has_medical_post: boolean;
  accessible: boolean;
  flood_safe: boolean;
}

export interface DamageDetection {
  damage_class: string;
  confidence: number;
  detector: string;
  note?: string | null;
}

export interface VisionAssessment {
  image_path: string;
  detections: DamageDetection[];
  dominant_class: string;
  severity_signal: Severity;
  description: string;
  models_used: string[];
  ensemble_agreement: number;
}

export interface WeatherIntel extends IntelligenceProduct {
  current_conditions: string;
  rainfall_mm_24h: number;
  forecast_rainfall_mm_24h: number;
  wind_speed_kmh: number;
  river_level_m?: number | null;
  river_danger_level_m?: number | null;
  flood_probability: number;
  escalation_expected: boolean;
  forecast_narrative: string;
  safe_operating_window_hours?: number | null;
}

export interface MedicalIntel extends IntelligenceProduct {
  casualty_projection: number;
  triage_categories: Record<string, number>;
  hospitals: HospitalStatus[];
  total_available_beds: number;
  bed_deficit: number;
  ambulances_required: number;
  disease_outbreak_risk: number;
  outbreak_watchlist: string[];
}

export interface ShelterIntel extends IntelligenceProduct {
  people_to_shelter: number;
  shelters: ShelterSite[];
  total_spare_capacity: number;
  capacity_deficit: number;
  evacuation_routes: string[];
  vulnerable_groups: string[];
}

export interface InfrastructureIntel extends IntelligenceProduct {
  roads_blocked: string[];
  bridges_at_risk: string[];
  access_corridors: string[];
  structural_risk_score: number;
  water_supply_status: string;
  vision_assessments: VisionAssessment[];
}

export interface KnowledgeBrief extends IntelligenceProduct {
  applicable_sops: string[];
  mandated_actions: string[];
  prohibited_actions: string[];
  retrieved_chunks: number;
}

export interface ImpactEstimate {
  population_at_risk: number;
  people_requiring_evacuation: number;
  people_requiring_medical_care: number;
  people_requiring_shelter: number;
  affected_radius_km: number;
  estimated_duration_hours: number;
}

export interface SituationAssessment {
  hazard_type: string;
  secondary_hazards: string[];
  severity: Severity;
  confidence: number;
  headline: string;
  summary: string;
  impact: ImpactEstimate;
  immediate_risks: string[];
  information_gaps: string[];
  evidence: string[];
}

export interface AgentDispatch {
  agent: AgentRole;
  reason: string;
  priority: number;
  focus_question: string;
}

export interface ActivationPlan {
  incident_id: string;
  dispatches: AgentDispatch[];
  declined: AgentDispatch[];
  command_intent: string;
  escalate_to_state: boolean;
  escalation_reason?: string | null;
}

export interface Allocation {
  allocation_id: string;
  resource_type: string;
  quantity: number;
  from_depot_name: string;
  to_location_name: string;
  to_point: GeoPoint;
  distance_km: number;
  eta_minutes: number;
  urgency: string;
  rationale: string;
}

export interface UnmetNeed {
  resource_type: string;
  quantity_short: number;
  beneficiaries_affected: number;
  escalation_path: string;
  consequence: string;
}

export interface ResourceRequirement {
  resource_type: string;
  quantity_required: number;
  urgency: string;
  justification: string;
  beneficiaries: number;
  deadline_hours: number;
}

export interface AllocationPlan {
  plan_id: string;
  requirements: ResourceRequirement[];
  allocations: Allocation[];
  unmet_needs: UnmetNeed[];
  strategy_narrative: string;
  coverage_ratio: number;
  total_units_allocated: number;
  depots_engaged: string[];
  organizations_engaged: string[];
  revision: number;
}

export interface CritiqueFinding {
  issue: string;
  severity: string;
  affected_component: string;
  suggested_fix: string;
}

export interface ReflectionVerdict {
  approved: boolean;
  overall_quality: number;
  findings: CritiqueFinding[];
  doctrine_compliance: number;
  internal_consistency: number;
  coverage_adequacy: number;
  revision_instruction?: string | null;
  cycle: number;
}

export interface CommunicationArtifact {
  channel: string;
  audience: string;
  subject: string;
  body: string;
  call_to_action: string[];
}

export interface CommunicationPackage {
  artifacts: CommunicationArtifact[];
  public_alert_headline: string;
  misinformation_guardrails: string[];
}

export interface OperationalPicture {
  incident_id: string;
  status: string;
  created_at: string;
  completed_at?: string | null;
  report: {
    incident_id: string;
    description: string;
    location: LocationRef;
    reported_at: string;
    media_paths: string[];
    reported_casualties?: number | null;
  };
  assessment?: SituationAssessment | null;
  activation_plan?: ActivationPlan | null;
  weather?: WeatherIntel | null;
  infrastructure?: InfrastructureIntel | null;
  medical?: MedicalIntel | null;
  shelter?: ShelterIntel | null;
  knowledge?: KnowledgeBrief | null;
  allocation_plan?: AllocationPlan | null;
  reflection?: ReflectionVerdict | null;
  reflection_history: ReflectionVerdict[];
  communications?: CommunicationPackage | null;
  consolidated_recommendations: Recommendation[];
  errors: string[];
}

export interface SubsystemStatus {
  name: string;
  available: boolean;
  detail: string;
  metadata: Record<string, unknown>;
}

export interface SystemStatus {
  app: string;
  version: string;
  environment: string;
  llm: SubsystemStatus;
  vision: SubsystemStatus;
  retrieval: SubsystemStatus;
  registries: SubsystemStatus;
  deterministic_mode: boolean;
  data_provenance: Record<string, { synthetic?: boolean; notice?: string }>;
}

export interface Scenario {
  key: string;
  title: string;
  description: string;
  demonstrates: string;
}

export interface RunAccepted {
  run_id: string;
  incident_id: string;
  stream_url: string;
  status_url: string;
}

export interface RegistryRecord {
  name: string;
  point: GeoPoint;
  [key: string]: unknown;
}

export interface RegistryResponse {
  kind: string;
  meta: Record<string, unknown>;
  records: RegistryRecord[];
}
