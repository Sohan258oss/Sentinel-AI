import { useState, type ReactNode } from "react";
import {
  SEVERITY_COLOR,
  formatNumber,
  formatPercent,
  titleCase,
} from "../lib/format";
import type {
  IntelligenceProduct,
  OperationalPicture,
} from "../lib/types";

type Tab = "assessment" | "intelligence" | "allocation" | "assurance" | "comms";

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: "assessment", label: "ASSESSMENT", icon: "📊" },
  { key: "intelligence", label: "INTELLIGENCE", icon: "📡" },
  { key: "allocation", label: "ALLOCATION", icon: "🚛" },
  { key: "assurance", label: "ASSURANCE", icon: "🛡️" },
  { key: "comms", label: "COMMS", icon: "📢" },
];

function Empty({ children }: { children: ReactNode }) {
  return (
    <p className="px-2 py-10 text-center font-mono text-[11px] text-ink-faint">
      {children}
    </p>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="rounded-lg border border-edge/80 bg-abyss/80 px-3 py-2 shadow-sm">
      <div className="font-mono text-[9.5px] font-bold tracking-wider text-ink-faint uppercase">
        {label}
      </div>
      <div
        className="mt-1 font-mono text-base font-bold tracking-tight"
        style={{ color: tone ?? "var(--color-ink)" }}
      >
        {value}
      </div>
    </div>
  );
}

function ProductCard({
  label,
  product,
}: {
  label: string;
  product: IntelligenceProduct | null | undefined;
}) {
  if (!product) {
    return (
      <div className="rounded-lg border border-edge/50 bg-panel/30 px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] font-semibold tracking-wide text-ink-faint">
            {label}
          </span>
          <span className="font-mono text-[9.5px] text-ink-faint italic">
            — not activated
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-edge/80 bg-panel/80 p-3 shadow-md">
      <div className="flex items-center justify-between gap-2 border-b border-edge/40 pb-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10.5px] font-bold tracking-wide text-signal">
            {label}
          </span>
          {product.degraded && (
            <span className="rounded bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.5 font-mono text-[8.5px] font-bold text-amber-400">
              DEGRADED
            </span>
          )}
        </div>
        <span className="font-mono text-[9.5px] font-medium text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
          CONF {formatPercent(product.confidence)}
        </span>
      </div>

      <p className="mt-2 text-[12px] font-semibold leading-snug text-ink">
        {product.headline}
      </p>

      <ul className="mt-2 space-y-1">
        {product.key_findings.slice(0, 5).map((finding, index) => (
          <li
            key={index}
            className="flex gap-2 text-[11px] leading-relaxed text-ink-dim"
          >
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-signal-deep" />
            <span>{finding}</span>
          </li>
        ))}
      </ul>

      {product.metrics.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {product.metrics.map((metric, index) => (
            <span
              key={index}
              className="rounded-md border border-edge bg-abyss px-2 py-1 font-mono text-[10px] text-ink-dim"
            >
              {metric.label}:{" "}
              <span className="font-bold text-ink">{formatNumber(metric.value)}</span>{" "}
              <span className="text-ink-faint">{metric.unit}</span>
            </span>
          ))}
        </div>
      )}

      {product.citations.length > 0 && (
        <div className="mt-3 space-y-1.5 border-t border-edge/60 pt-2">
          {product.citations.slice(0, 3).map((citation, index) => (
            <div key={index} className="text-[10px] leading-relaxed">
              <span className="font-mono font-semibold text-purple-400">
                {citation.source_id}
              </span>
              {citation.section && (
                <span className="text-ink-faint"> §{citation.section}</span>
              )}
              <span className="text-ink-faint">
                {" "}
                · {formatPercent(citation.relevance)} relevance
              </span>
              <p className="text-ink-faint italic mt-0.5">
                "{citation.snippet.slice(0, 140)}…"
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function OperationalPanels({
  picture,
  onClose,
  onMinimize,
}: {
  picture: OperationalPicture | null;
  onClose?: () => void;
  onMinimize?: () => void;
}) {
  const [tab, setTab] = useState<Tab>("assessment");

  return (
    <div className="flex h-full flex-col bg-panel/90 backdrop-blur-md">
      <div className="flex shrink-0 items-center justify-between border-b border-edge/80 bg-abyss/60 px-2 pt-1.5">
        <div className="flex items-center gap-1">
          {TABS.map((entry) => (
            <button
              key={entry.key}
              onClick={() => setTab(entry.key)}
              className={`flex items-center gap-1.5 rounded-t-lg px-3 py-2 font-mono text-[10px] font-bold tracking-wider transition-all ${
                tab === entry.key
                  ? "border-t-2 border-signal bg-panel text-signal shadow-sm"
                  : "text-ink-faint hover:bg-panel/40 hover:text-ink"
              }`}
            >
              <span>{entry.icon}</span>
              {entry.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1.5 pr-2">
          {onMinimize && (
            <button
              onClick={onMinimize}
              title="Minimize Operational Analysis"
              className="flex items-center gap-1 rounded bg-panel-raised/80 px-2 py-1 font-mono text-[10px] font-semibold text-ink-dim hover:bg-edge hover:text-ink transition-colors"
            >
              <span>▼</span> Minimize
            </button>
          )}
          {onClose && (
            <button
              onClick={onClose}
              title="Close Panel (Go Back to Map)"
              className="flex items-center gap-1 rounded bg-panel-raised/80 px-2.5 py-1 font-mono text-[10px] font-bold text-red-400/90 hover:bg-red-500/20 hover:text-red-400 transition-colors"
            >
              <span>✕</span> Close
            </button>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {!picture && <Empty>Run a scenario or custom incident to populate operational analysis.</Empty>}

        {picture && tab === "assessment" && (
          <AssessmentTab picture={picture} />
        )}
        {picture && tab === "intelligence" && (
          <div className="space-y-2">
            <ProductCard label="WEATHER · SDG 13" product={picture.weather} />
            <ProductCard
              label="INFRASTRUCTURE · SDG 9"
              product={picture.infrastructure}
            />
            <ProductCard label="MEDICAL · SDG 3" product={picture.medical} />
            <ProductCard label="SHELTER · SDG 11" product={picture.shelter} />
            <ProductCard label="DOCTRINE · RAG" product={picture.knowledge} />
          </div>
        )}
        {picture && tab === "allocation" && <AllocationTab picture={picture} />}
        {picture && tab === "assurance" && <AssuranceTab picture={picture} />}
        {picture && tab === "comms" && <CommsTab picture={picture} />}
      </div>
    </div>
  );
}

function AssessmentTab({ picture }: { picture: OperationalPicture }) {
  const assessment = picture.assessment;
  const plan = picture.activation_plan;
  if (!assessment) return <Empty>No assessment produced.</Empty>;

  const color = SEVERITY_COLOR[assessment.severity];

  return (
    <div className="space-y-2">
      <div
        className="rounded border-l-2 bg-panel px-3 py-2"
        style={{ borderColor: color }}
      >
        <div className="flex items-center gap-2">
          <span
            className="rounded px-1.5 py-0.5 font-mono text-[9px] font-semibold tracking-wide"
            style={{ background: `${color}22`, color }}
          >
            {assessment.severity.toUpperCase()}
          </span>
          <span className="font-mono text-[9px] text-ink-dim">
            {titleCase(assessment.hazard_type)}
          </span>
          <span className="ml-auto font-mono text-[9px] text-ink-faint">
            confidence {formatPercent(assessment.confidence)}
          </span>
        </div>
        <p className="mt-1.5 text-sm font-medium text-ink">
          {assessment.headline}
        </p>
        <p className="mt-1 text-[11px] leading-relaxed text-ink-dim">
          {assessment.summary}
        </p>
      </div>

      <div className="grid grid-cols-4 gap-1.5">
        <Stat
          label="AT RISK"
          value={formatNumber(assessment.impact.population_at_risk)}
        />
        <Stat
          label="EVACUATION"
          value={formatNumber(assessment.impact.people_requiring_evacuation)}
        />
        <Stat
          label="MEDICAL"
          value={formatNumber(assessment.impact.people_requiring_medical_care)}
        />
        <Stat
          label="SHELTER"
          value={formatNumber(assessment.impact.people_requiring_shelter)}
        />
      </div>

      {assessment.immediate_risks.length > 0 && (
        <div className="rounded border border-edge bg-panel px-2.5 py-2">
          <h3 className="font-mono text-[9px] tracking-wide text-orange-400">
            IMMEDIATE RISKS
          </h3>
          <ul className="mt-1 space-y-0.5">
            {assessment.immediate_risks.map((risk, index) => (
              <li
                key={index}
                className="flex gap-1.5 text-[10.5px] leading-snug text-ink-dim"
              >
                <span className="text-orange-400">▸</span>
                {risk}
              </li>
            ))}
          </ul>
        </div>
      )}

      {assessment.secondary_hazards.length > 0 && (
        <div className="rounded border border-edge bg-panel px-2.5 py-2">
          <h3 className="font-mono text-[9px] tracking-wide text-ink-dim">
            CASCADING HAZARDS
          </h3>
          <div className="mt-1 flex flex-wrap gap-1">
            {assessment.secondary_hazards.map((hazard) => (
              <span
                key={hazard}
                className="rounded bg-panel-raised px-1.5 py-0.5 font-mono text-[9px] text-amber-400"
              >
                {titleCase(hazard)}
              </span>
            ))}
          </div>
        </div>
      )}

      {plan && (
        <div className="rounded border border-edge bg-panel px-2.5 py-2">
          <h3 className="font-mono text-[9px] tracking-wide text-signal">
            COMMANDER'S INTENT
          </h3>
          <p className="mt-1 text-[10.5px] leading-relaxed text-ink-dim">
            {plan.command_intent}
          </p>

          <div className="mt-2 space-y-1">
            {plan.dispatches.map((dispatch) => (
              <div key={dispatch.agent} className="text-[10px] leading-snug">
                <span className="font-mono text-emerald-400">
                  P{dispatch.priority} {dispatch.agent}
                </span>
                {dispatch.focus_question && (
                  <p className="text-ink-faint">→ {dispatch.focus_question}</p>
                )}
              </div>
            ))}
            {plan.declined.map((dispatch) => (
              <div
                key={dispatch.agent}
                className="text-[10px] leading-snug text-ink-faint"
              >
                <span className="font-mono line-through">{dispatch.agent}</span>{" "}
                <span>{dispatch.reason}</span>
              </div>
            ))}
          </div>

          {plan.escalate_to_state && (
            <div className="mt-2 rounded bg-red-500/10 px-2 py-1">
              <span className="font-mono text-[9px] text-red-400">
                ESCALATED TO STATE
              </span>
              <p className="text-[10px] text-ink-dim">
                {plan.escalation_reason}
              </p>
            </div>
          )}
        </div>
      )}

      {assessment.information_gaps.length > 0 && (
        <div className="rounded border border-edge bg-panel px-2.5 py-2">
          <h3 className="font-mono text-[9px] tracking-wide text-ink-dim">
            INFORMATION GAPS
          </h3>
          <ul className="mt-1 space-y-0.5">
            {assessment.information_gaps.map((gap, index) => (
              <li key={index} className="text-[10px] text-ink-faint">
                ? {gap}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function AllocationTab({ picture }: { picture: OperationalPicture }) {
  const plan = picture.allocation_plan;
  if (!plan) return <Empty>No allocation plan produced.</Empty>;

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-4 gap-1.5">
        <Stat
          label="COVERAGE"
          value={formatPercent(plan.coverage_ratio)}
          tone={plan.coverage_ratio > 0.8 ? "#4ade80" : "#fb923c"}
        />
        <Stat label="UNITS" value={formatNumber(plan.total_units_allocated)} />
        <Stat label="DISPATCHES" value={String(plan.allocations.length)} />
        <Stat
          label="PARTNERS"
          value={String(plan.organizations_engaged.length)}
          tone="#818cf8"
        />
      </div>

      {plan.strategy_narrative && (
        <div className="rounded border border-edge bg-panel px-2.5 py-2">
          <h3 className="font-mono text-[9px] tracking-wide text-signal">
            STRATEGY
          </h3>
          <p className="mt-1 text-[10.5px] leading-relaxed text-ink-dim">
            {plan.strategy_narrative}
          </p>
        </div>
      )}

      {plan.unmet_needs.length > 0 && (
        <div className="rounded border border-red-500/30 bg-red-500/5 px-2.5 py-2">
          <h3 className="font-mono text-[9px] tracking-wide text-red-400">
            UNMET NEEDS — ESCALATION REQUIRED
          </h3>
          <div className="mt-1 space-y-1.5">
            {plan.unmet_needs.map((unmet, index) => (
              <div key={index}>
                <div className="flex items-baseline gap-1.5 text-[10.5px]">
                  <span className="font-mono text-red-400">
                    SHORT {formatNumber(unmet.quantity_short)}
                  </span>
                  <span className="text-ink">
                    {titleCase(unmet.resource_type)}
                  </span>
                  <span className="ml-auto font-mono text-[9px] text-ink-faint">
                    {formatNumber(unmet.beneficiaries_affected)} affected
                  </span>
                </div>
                <p className="text-[9.5px] leading-snug text-ink-faint">
                  {unmet.consequence}
                </p>
                <p className="text-[9.5px] leading-snug text-amber-400/80">
                  → {unmet.escalation_path}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded border border-edge">
        <table className="w-full text-left">
          <thead className="bg-panel-raised">
            <tr className="font-mono text-[8.5px] tracking-wide text-ink-faint">
              <th className="px-2 py-1">QTY</th>
              <th className="px-2 py-1">RESOURCE</th>
              <th className="px-2 py-1">SOURCE</th>
              <th className="px-2 py-1 text-right">ETA</th>
            </tr>
          </thead>
          <tbody>
            {plan.allocations.map((allocation) => (
              <tr
                key={allocation.allocation_id}
                className="border-t border-edge text-[10px] hover:bg-panel-raised"
              >
                <td className="px-2 py-1 font-mono text-ink">
                  {formatNumber(allocation.quantity)}
                </td>
                <td className="px-2 py-1 text-ink-dim">
                  {titleCase(allocation.resource_type)}
                </td>
                <td className="truncate px-2 py-1 text-ink-faint">
                  {allocation.from_depot_name}
                </td>
                <td className="px-2 py-1 text-right font-mono text-ink-dim">
                  {allocation.eta_minutes}m
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AssuranceTab({ picture }: { picture: OperationalPicture }) {
  const reflection = picture.reflection;
  if (!reflection) return <Empty>No assurance review recorded.</Empty>;

  const severityTone: Record<string, string> = {
    blocking: "#ef4444",
    major: "#fb923c",
    minor: "#facc15",
  };

  return (
    <div className="space-y-2">
      <div
        className={`rounded border-l-2 bg-panel px-3 py-2 ${
          reflection.approved ? "border-emerald-400" : "border-orange-400"
        }`}
      >
        <div className="flex items-center gap-2">
          <span
            className={`font-mono text-[11px] font-semibold ${
              reflection.approved ? "text-emerald-400" : "text-orange-400"
            }`}
          >
            {reflection.approved ? "APPROVED" : "REVISION REQUIRED"}
          </span>
          <span className="ml-auto font-mono text-[9px] text-ink-faint">
            {picture.reflection_history.length} cycle
            {picture.reflection_history.length === 1 ? "" : "s"}
          </span>
        </div>
        {reflection.revision_instruction && (
          <p className="mt-1 text-[10.5px] leading-snug text-ink-dim">
            {reflection.revision_instruction}
          </p>
        )}
      </div>

      <div className="grid grid-cols-4 gap-1.5">
        <Stat label="QUALITY" value={formatPercent(reflection.overall_quality)} />
        <Stat
          label="CONSISTENCY"
          value={formatPercent(reflection.internal_consistency)}
        />
        <Stat
          label="DOCTRINE"
          value={formatPercent(reflection.doctrine_compliance)}
        />
        <Stat
          label="COVERAGE"
          value={formatPercent(reflection.coverage_adequacy)}
        />
      </div>

      <div className="space-y-1">
        {reflection.findings.map((finding, index) => (
          <div
            key={index}
            className="rounded border border-edge bg-panel px-2.5 py-1.5"
          >
            <div className="flex items-baseline gap-1.5">
              <span
                className="font-mono text-[8.5px] font-semibold tracking-wide"
                style={{ color: severityTone[finding.severity] ?? "#94a3bd" }}
              >
                {finding.severity.toUpperCase()}
              </span>
              <span className="font-mono text-[8.5px] text-ink-faint">
                {finding.affected_component}
              </span>
            </div>
            <p className="mt-0.5 text-[10.5px] leading-snug text-ink">
              {finding.issue}
            </p>
            <p className="mt-0.5 text-[10px] leading-snug text-emerald-400/80">
              fix: {finding.suggested_fix}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function CommsTab({ picture }: { picture: OperationalPicture }) {
  const comms = picture.communications;
  if (!comms) return <Empty>No communications package produced.</Empty>;

  return (
    <div className="space-y-2">
      {comms.public_alert_headline && (
        <div className="rounded border border-signal-deep bg-signal/5 px-3 py-2">
          <h3 className="font-mono text-[9px] tracking-wide text-signal">
            PUBLIC ALERT HEADLINE
          </h3>
          <p className="mt-1 text-sm font-semibold text-ink">
            {comms.public_alert_headline}
          </p>
        </div>
      )}

      {comms.artifacts.map((artifact, index) => (
        <div
          key={index}
          className="rounded border border-edge bg-panel px-2.5 py-2"
        >
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-[9px] tracking-wide text-signal">
              {artifact.channel.toUpperCase()}
            </span>
            <span className="font-mono text-[9px] text-ink-faint">
              → {artifact.audience}
            </span>
          </div>
          <p className="mt-1 text-[10.5px] font-medium text-ink">
            {artifact.subject}
          </p>
          <p className="mt-1 text-[10.5px] leading-relaxed text-ink-dim">
            {artifact.body}
          </p>
          {artifact.call_to_action.length > 0 && (
            <ul className="mt-1.5 space-y-0.5">
              {artifact.call_to_action.map((action, actionIndex) => (
                <li
                  key={actionIndex}
                  className="text-[10px] leading-snug text-emerald-400/80"
                >
                  ▸ {action}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}

      {comms.misinformation_guardrails.length > 0 && (
        <div className="rounded border border-amber-500/30 bg-amber-500/5 px-2.5 py-2">
          <h3 className="font-mono text-[9px] tracking-wide text-amber-400">
            MISINFORMATION GUARDRAILS
          </h3>
          <ul className="mt-1 space-y-1">
            {comms.misinformation_guardrails.map((guard, index) => (
              <li
                key={index}
                className="text-[10px] leading-snug text-ink-dim"
              >
                ▸ {guard}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
