import { useState } from "react";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (payload: Record<string, unknown>) => void;
  disabled?: boolean;
}

const SAMPLE_LOCATIONS = [
  { name: "Guwahati", district: "Kamrup Metropolitan", state: "Assam", lat: 26.1445, lon: 91.7362, pop: 1100000 },
  { name: "Kedarnath / Chamoli", district: "Rudraprayag", state: "Uttarakhand", lat: 30.7346, lon: 79.0669, pop: 250000 },
  { name: "Mumbai", district: "Mumbai Suburban", state: "Maharashtra", lat: 19.0760, lon: 72.8777, pop: 12500000 },
  { name: "Puri", district: "Puri", state: "Odisha", lat: 19.8135, lon: 85.8312, pop: 200000 },
  { name: "Delhi NCR", district: "Central Delhi", state: "Delhi", lat: 28.6139, lon: 77.2090, pop: 11000000 },
];

export function CustomIncidentModal({ isOpen, onClose, onSubmit, disabled }: Props) {
  const [name, setName] = useState("Guwahati");
  const [district, setDistrict] = useState("Kamrup Metropolitan");
  const [stateName, setStateName] = useState("Assam");
  const [latitude, setLatitude] = useState(26.1445);
  const [longitude, setLongitude] = useState(91.7362);
  const [population, setPopulation] = useState(1100000);
  const [hazard, setHazard] = useState("flood");
  const [casualties, setCasualties] = useState(12);
  const [description, setDescription] = useState(
    "Severe flash flood and urban waterlogging reported across primary transit corridors. Multiple residential areas inundated."
  );

  if (!isOpen) return null;

  const handleSelectSample = (sample: typeof SAMPLE_LOCATIONS[0]) => {
    setName(sample.name);
    setDistrict(sample.district);
    setStateName(sample.state);
    setLatitude(sample.lat);
    setLongitude(sample.lon);
    setPopulation(sample.pop);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      description,
      location_name: name,
      district,
      state: stateName,
      latitude: Number(latitude),
      longitude: Number(longitude),
      population: Number(population),
      declared_hazard: hazard,
      reported_casualties: Number(casualties),
      channel: "control_room",
      verified: true,
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/85 p-4 backdrop-blur-lg">
      <div className="w-full max-w-xl rounded-xl border border-edge-bright bg-panel/95 p-6 shadow-2xl transition-all">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-edge/80 pb-3.5">
          <div>
            <h2 className="font-mono text-base font-bold tracking-wider text-signal uppercase flex items-center gap-2">
              <span className="size-2.5 rounded-full bg-signal pulse-ring" />
              Report Custom Incident (All-India)
            </h2>
            <p className="mt-0.5 text-xs text-ink-dim">
              Submit a real-time incident in India to activate autonomous agent dispatch.
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-ink-faint hover:bg-edge hover:text-ink transition-colors"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4">
          {/* Quick presets */}
          <div>
            <label className="font-mono text-[10px] font-bold uppercase text-ink-faint tracking-wider">
              Quick Location Presets:
            </label>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {SAMPLE_LOCATIONS.map((loc) => (
                <button
                  key={loc.name}
                  type="button"
                  onClick={() => handleSelectSample(loc)}
                  className={`rounded-md border px-2.5 py-1 font-mono text-[10.5px] transition-all ${
                    name === loc.name
                      ? "border-signal bg-signal/20 text-signal font-bold"
                      : "border-edge/60 bg-abyss/80 text-ink-dim hover:border-signal/60 hover:text-ink"
                  }`}
                >
                  {loc.name} ({loc.state})
                </button>
              ))}
            </div>
          </div>

          {/* Form fields */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="font-mono text-[10px] font-bold uppercase text-ink-faint tracking-wider">
                Location Name *
              </label>
              <input
                required
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 w-full rounded-md border border-edge/80 bg-abyss/90 px-3 py-1.5 font-mono text-xs text-ink focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
              />
            </div>
            <div>
              <label className="font-mono text-[10px] font-bold uppercase text-ink-faint tracking-wider">
                District
              </label>
              <input
                type="text"
                value={district}
                onChange={(e) => setDistrict(e.target.value)}
                className="mt-1 w-full rounded-md border border-edge/80 bg-abyss/90 px-3 py-1.5 font-mono text-xs text-ink focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
              />
            </div>
            <div>
              <label className="font-mono text-[10px] font-bold uppercase text-ink-faint tracking-wider">
                State
              </label>
              <input
                type="text"
                value={stateName}
                onChange={(e) => setStateName(e.target.value)}
                className="mt-1 w-full rounded-md border border-edge/80 bg-abyss/90 px-3 py-1.5 font-mono text-xs text-ink focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
              />
            </div>
          </div>

          <div className="grid grid-cols-4 gap-3">
            <div>
              <label className="font-mono text-[10px] font-bold uppercase text-ink-faint tracking-wider">
                Latitude *
              </label>
              <input
                required
                type="number"
                step="any"
                value={latitude}
                onChange={(e) => setLatitude(parseFloat(e.target.value))}
                className="mt-1 w-full rounded-md border border-edge/80 bg-abyss/90 px-3 py-1.5 font-mono text-xs text-ink focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
              />
            </div>
            <div>
              <label className="font-mono text-[10px] font-bold uppercase text-ink-faint tracking-wider">
                Longitude *
              </label>
              <input
                required
                type="number"
                step="any"
                value={longitude}
                onChange={(e) => setLongitude(parseFloat(e.target.value))}
                className="mt-1 w-full rounded-md border border-edge/80 bg-abyss/90 px-3 py-1.5 font-mono text-xs text-ink focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
              />
            </div>
            <div>
              <label className="font-mono text-[10px] font-bold uppercase text-ink-faint tracking-wider">
                Population
              </label>
              <input
                type="number"
                value={population}
                onChange={(e) => setPopulation(parseInt(e.target.value) || 0)}
                className="mt-1 w-full rounded-md border border-edge/80 bg-abyss/90 px-3 py-1.5 font-mono text-xs text-ink focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
              />
            </div>
            <div>
              <label className="font-mono text-[10px] font-bold uppercase text-ink-faint tracking-wider">
                Casualties
              </label>
              <input
                type="number"
                value={casualties}
                onChange={(e) => setCasualties(parseInt(e.target.value) || 0)}
                className="mt-1 w-full rounded-md border border-edge/80 bg-abyss/90 px-3 py-1.5 font-mono text-xs text-ink focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
              />
            </div>
          </div>

          <div>
            <label className="font-mono text-[10px] font-bold uppercase text-ink-faint tracking-wider">
              Hazard Type
            </label>
            <select
              value={hazard}
              onChange={(e) => setHazard(e.target.value)}
              className="mt-1 w-full rounded-md border border-edge/80 bg-abyss/90 px-3 py-1.5 font-mono text-xs text-ink focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
            >
              <option value="flood">Flood</option>
              <option value="urban_flood">Urban Flood</option>
              <option value="cyclone">Cyclone</option>
              <option value="earthquake">Earthquake</option>
              <option value="landslide">Landslide</option>
              <option value="heatwave">Heatwave</option>
              <option value="building_collapse">Building Collapse</option>
              <option value="wildfire">Wildfire</option>
              <option value="industrial_chemical">Industrial Chemical</option>
              <option value="epidemic">Epidemic</option>
            </select>
          </div>

          <div>
            <label className="font-mono text-[10px] font-bold uppercase text-ink-faint tracking-wider">
              Incident Description *
            </label>
            <textarea
              required
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="mt-1 w-full rounded-md border border-edge/80 bg-abyss/90 px-3 py-1.5 font-mono text-xs text-ink focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
            />
          </div>

          <div className="mt-2 flex justify-end gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-edge px-4 py-1.5 font-mono text-xs font-medium text-ink-dim hover:bg-edge transition-colors"
            >
              Cancel
            </button>
            <button
              disabled={disabled}
              type="submit"
              className="rounded-md bg-signal px-5 py-1.5 font-mono text-xs font-bold text-void hover:bg-signal-deep disabled:opacity-50 transition-all shadow-md"
            >
              Dispatch Agent Response →
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

