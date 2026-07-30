interface ActionStep {
  step: number;
  title: string;
  detail: string;
}

interface ActionPlanData {
  disaster: string;
  threat_level: string;
  summary: string;
  actions: ActionStep[];
  helplines: string[];
}

interface Props {
  plan: ActionPlanData | null;
  districtName?: string;
  stateName?: string;
}

export function CitizenActionPlanCard({ plan, districtName, stateName }: Props) {
  if (!plan) return null;

  const isCritical = plan.threat_level === "CRITICAL";
  const isSevere = plan.threat_level === "SEVERE";
  const badgeColor = isCritical ? "#ef4444" : isSevere ? "#f97316" : "#eab308";

  return (
    <div
      className="rounded-xl border p-4 shadow-2xl backdrop-blur-md transition-all"
      style={{
        background: "rgba(10, 15, 29, 0.95)",
        borderColor: `${badgeColor}60`,
        boxShadow: `0 0 30px ${badgeColor}20`,
      }}
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-edge/60 pb-3">
        <div className="flex items-center gap-2">
          <span
            className="flex size-7 items-center justify-center rounded-full font-mono text-sm font-bold text-void animate-pulse"
            style={{ background: badgeColor }}
          >
            !
          </span>
          <div>
            <h2 className="font-mono text-sm font-extrabold uppercase tracking-wider text-ink flex items-center gap-2">
              EMERGENCY SOLUTION — WHAT TO DO RIGHT NOW
            </h2>
            <p className="text-[11px] font-semibold text-ink-dim">
              Verified NDMA / NDRF Safety Protocol for {districtName || "District"}{stateName ? `, ${stateName}` : ""}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span
            className="rounded px-2 py-0.5 font-mono text-[10px] font-extrabold uppercase tracking-wider text-void"
            style={{ background: badgeColor }}
          >
            {plan.threat_level} THREAT
          </span>
          <span className="font-mono text-[10.5px] font-bold text-signal bg-signal/15 px-2.5 py-0.5 rounded border border-signal/30">
            {plan.disaster}
          </span>
        </div>
      </div>

      {/* Summary */}
      <p className="mt-2.5 text-xs font-semibold leading-relaxed text-ink-dim bg-abyss/80 p-2.5 rounded-lg border border-edge/60">
        💡 <strong className="text-ink">Citizen Guidance:</strong> {plan.summary}
      </p>

      {/* Action Steps Grid */}
      <div className="mt-3.5 space-y-2.5">
        {plan.actions.map((act) => (
          <div
            key={act.step}
            className="group flex items-start gap-3 rounded-lg border border-edge/80 bg-panel-raised/70 p-3 transition-all hover:border-signal/60 hover:bg-panel-raised"
          >
            <span
              className="flex size-6 shrink-0 items-center justify-center rounded-full font-mono text-xs font-black text-void shadow-md"
              style={{ background: badgeColor }}
            >
              {act.step}
            </span>
            <div className="min-w-0 flex-1">
              <h4 className="font-mono text-xs font-extrabold text-ink group-hover:text-signal">
                {act.title}
              </h4>
              <p className="mt-0.5 text-[11.5px] leading-relaxed text-ink-dim">
                {act.detail}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Helplines Footer */}
      {plan.helplines && plan.helplines.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-edge/60 pt-3">
          <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1">
            📞 Emergency Helpline Numbers:
          </span>
          <div className="flex flex-wrap gap-1.5">
            {plan.helplines.map((h, i) => (
              <span
                key={i}
                className="rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] font-bold text-emerald-300"
              >
                {h}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
