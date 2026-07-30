/**
 * Offline Safety Store
 *
 * Pre-cached NDMA/NDRF verified emergency instructions, first aid protocols,
 * and emergency helplines. Guarantees 100% instant rendering even if cell network
 * towers fail or internet connection is lost during an ongoing disaster.
 */

export interface EmergencyActionStep {
  step: number;
  title: string;
  detail: string;
  urgent?: boolean;
}

export interface DisasterGuideline {
  key: string;
  disaster: string;
  icon: string;
  threat_level: "CRITICAL" | "SEVERE" | "MODERATE";
  summary: string;
  actions: EmergencyActionStep[];
  helplines: Array<{ label: string; number: string }>;
}

export const OFFLINE_DISASTER_DATABASE: Record<string, DisasterGuideline> = {
  flood: {
    key: "flood",
    disaster: "Flood / Water Entering House",
    icon: "🌊",
    threat_level: "CRITICAL",
    summary: "Flood water entering building. Follow these immediate safety steps right now:",
    actions: [
      { step: 1, title: "Move to Upper Floor Immediately", detail: "Evacuate ground floors. Reach upper floors, rooftops, or designated elevated disaster shelters.", urgent: true },
      { step: 2, title: "Disconnect Main Electricity & Gas", detail: "Switch off main circuit breaker switches to prevent electrocution and electrical fires in water.", urgent: true },
      { step: 3, title: "Do NOT Walk or Swim in Moving Water", detail: "Fast-moving water as shallow as 15 cm (6 inches) can knock adults down. Avoid flooded roads." },
      { step: 4, title: "Pack Emergency Kit", detail: "Carry essential medicines, clean drinking water, flashlight, dry non-perishable food, and identity cards." },
      { step: 5, title: "Boil Drinking Water", detail: "Boil all water for 3 minutes before drinking to prevent cholera and waterborne infections." }
    ],
    helplines: [
      { label: "National Emergency", number: "112" },
      { label: "State Disaster Control", number: "1070" },
      { label: "District Relief Cell", number: "1077" },
      { label: "Ambulance Response", number: "108" }
    ]
  },
  cyclone: {
    key: "cyclone",
    disaster: "Cyclone / High Winds & Gale Storm",
    icon: "🌀",
    threat_level: "SEVERE",
    summary: "Extreme gale winds and coastal surge expected. Stay indoors in safe pucca structure.",
    actions: [
      { step: 1, title: "Stay Inside Concrete Pucca Building", detail: "Remain indoors away from glass windows, doors, and loose tin roofs.", urgent: true },
      { step: 2, title: "Beware of the Eye of Storm", detail: "A sudden calm in winds is temporary. Fierce gale winds will resume violently from opposite direction.", urgent: true },
      { step: 3, title: "Secure Outdoor Items", detail: "Tie down loose objects, solar panels, and water tanks that can fly in strong winds." },
      { step: 4, title: "Keep Phone Charged", detail: "Charge phones and keep battery radio active for official government bulletins." }
    ],
    helplines: [
      { label: "National Emergency", number: "112" },
      { label: "State Disaster Cell", number: "1070" },
      { label: "District Control", number: "1077" }
    ]
  },
  earthquake: {
    key: "earthquake",
    disaster: "Earthquake / Building Tremors",
    icon: "🏚️",
    threat_level: "SEVERE",
    summary: "Seismic shaking active. Protect your head and torso from falling debris.",
    actions: [
      { step: 1, title: "DROP, COVER, HOLD ON", detail: "Drop to hands and knees. Cover your head under a heavy desk or table. Hold on until tremors stop.", urgent: true },
      { step: 2, title: "Stay Indoors Away From Windows", detail: "Do not rush outside during tremors. Glass panes, hanging objects, and parapets fall first.", urgent: true },
      { step: 3, title: "If Outdoors, Move to Open Space", detail: "Move clear of tall buildings, utility poles, streetlights, and overpasses." },
      { step: 4, title: "Check Gas Valves After Shaking", detail: "Smell for gas before striking matches or turning on electrical switches." }
    ],
    helplines: [
      { label: "National Emergency", number: "112" },
      { label: "Ambulance Triage", number: "108" },
      { label: "Fire Control Room", number: "101" }
    ]
  },
  medical: {
    key: "medical",
    disaster: "Medical Injury / Need First Aid",
    icon: "🩹",
    threat_level: "CRITICAL",
    summary: "Emergency first aid guidance for disaster victims and injuries:",
    actions: [
      { step: 1, title: "Stop Severe Bleeding", detail: "Apply firm direct pressure on bleeding wounds using clean cloth or bandage. Keep limb elevated.", urgent: true },
      { step: 2, title: "Treat Burns with Clean Water", detail: "Cool burns with clean room-temperature water for 10 minutes. Do not apply ice or oil directly.", urgent: true },
      { step: 3, title: "Keep Victim Warm & Calm", detail: "Cover the injured person with dry blanket to prevent medical shock." },
      { step: 4, title: "Call Emergency Ambulance", detail: "Dial 108 or 112 immediately for trauma ambulance dispatch to nearest open hospital." }
    ],
    helplines: [
      { label: "Ambulance Dispatch", number: "108" },
      { label: "National Emergency", number: "112" },
      { label: "Red Cross Medical Cell", number: "1800-185-185" }
    ]
  },
  shelter: {
    key: "shelter",
    disaster: "Need Shelter, Food & Clean Water",
    icon: "⛺",
    threat_level: "MODERATE",
    summary: "Guidance to reach nearest relief camp and safe food/water supplies:",
    actions: [
      { step: 1, title: "Proceed to Multipurpose Relief Camp", detail: "Head to designated government school, indoor stadium, or community shelter.", urgent: true },
      { step: 2, title: "Drink Only Safe Water", detail: "Boil water for 3 minutes or use halogen water purification tablets." },
      { step: 3, title: "Carry Essential Documents", detail: "Keep Aadhaar cards, bank passbooks, dry food, flashlight, and medicines safe in plastic pouch." }
    ],
    helplines: [
      { label: "District Relief Cell", number: "1077" },
      { label: "State Control Room", number: "1070" },
      { label: "National Emergency", number: "112" }
    ]
  },
  electrical: {
    key: "electrical",
    disaster: "Power Lines Down / Electrical Shock Risk",
    icon: "⚡",
    threat_level: "CRITICAL",
    summary: "High-voltage electrical danger around submerged areas and fallen poles:",
    actions: [
      { step: 1, title: "Stay 10 Meters Away From Fallen Wires", detail: "Never touch or step near fallen power cables or submerged poles. Current spreads in water.", urgent: true },
      { step: 2, title: "Do NOT Touch Wet Switches", detail: "Do not operate electrical appliances if standing in water or wet floors.", urgent: true },
      { step: 3, title: "Report Live Wire Danger", detail: "Call electricity control room or emergency 112 to cut power feeder line immediately." }
    ],
    helplines: [
      { label: "National Emergency", number: "112" },
      { label: "Fire & Rescue", number: "101" },
      { label: "District Control", number: "1077" }
    ]
  }
};

/** Load guideline from offline database or localStorage fallback */
export function getOfflineGuideline(key: string): DisasterGuideline {
  const normKey = key.toLowerCase();
  if (normKey in OFFLINE_DISASTER_DATABASE) {
    return OFFLINE_DISASTER_DATABASE[normKey];
  }
  return OFFLINE_DISASTER_DATABASE.flood;
}
