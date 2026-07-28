<div align="center">

# SentinelAI

**Autonomous Multi-Agent Disaster Intelligence & Resilience Platform**

*Predict. Coordinate. Respond. Recover.*

</div>

---

## What this is

An AI **Emergency Operations Centre**, not a chatbot with a map.

An incident arrives. A Situation Analysis officer triages it using live
hydrology, meteorology and a fine-tuned damage-classification CNN. An Incident
Commander decides *which specialists this particular incident warrants* and
tasks each with a specific question. Those specialists run **in parallel**,
each calling real tools. Their findings converge on a constrained optimiser
that produces an auditable dispatch plan across seven partner organisations. A
Reflection officer then **audits that plan and can send it back for revision**.
Only once it passes does the Communication officer write the public alert, the
responder brief, the government sitrep, the hospital advisory and the
volunteer tasking.

Every step streams live to the operator over SSE.

```
                          ┌──────────────┐
   incident report  ──▶   │   INTAKE     │
                          └──────┬───────┘
                                 ▼
                          ┌──────────────┐
                          │  SITUATION   │  ReAct + vision + structured triage
                          │   ANALYSIS   │
                          └──────┬───────┘
                                 ▼
                          ┌──────────────┐
                          │  COMMANDER   │  ◀── ① CONDITIONAL ROUTING
                          └──────┬───────┘
                                 │
        ┌──────────┬─────────────┼─────────────┬──────────┐  ② PARALLEL FAN-OUT
        ▼          ▼             ▼             ▼          ▼
   ┌────────┐ ┌─────────┐ ┌────────────┐ ┌────────┐ ┌──────────┐
   │WEATHER │ │ MEDICAL │ │INFRASTRUCT.│ │SHELTER │ │KNOWLEDGE │
   └────┬───┘ └────┬────┘ └─────┬──────┘ └───┬────┘ └────┬─────┘
        └──────────┴─────────────┼───────────┴───────────┘
                                 ▼                           ③ REDUCER FAN-IN
                          ┌──────────────┐
                          │  ALLOCATION  │  optimiser + LLM narration
                          └──────┬───────┘
                                 ▼
                          ┌──────────────┐
                          │  REFLECTION  │ ──── critique ────┐  ④ BOUNDED CYCLE
                          └──────┬───────┘                   │
                                 │ approved            revise│
                                 ▼                           │
                          ┌──────────────┐                   │
                          │COMMUNICATION │ ◀─────────────────┘
                          └──────────────┘
```

This is **Pattern 5 — Hybrid LangGraph Branching**: conditional routing,
parallel fan-out, reducer-based join, and a bounded cycle, in one graph.

---

## Quick start

```bash
git clone <repo> && cd "Sentinel AI"
```

**Backend**

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.rag.ingest --reset --probe     # build the doctrine index
.venv/bin/python -m uvicorn app.main:app --port 8000
```

**Frontend**

```bash
cd frontend && npm install && npm run dev     # http://localhost:5173
```

**Try it without the UI**

```bash
cd backend
.venv/bin/python -m app.cli scenarios
.venv/bin/python -m app.cli run kerala_flood --trace
```

### Optional: enable model reasoning

The platform runs fully without an API key — see *Deterministic mode* below.
To enable LLM reasoning, copy `backend/.env.example` to `backend/.env` and set:

```
SENTINEL_GOOGLE_API_KEY=your-key-here
```

### Optional: retrain the vision model

```bash
cd backend
.venv/bin/python -m ml.prepare_dataset            # downloads AIDER (275 MB, CC-BY-4.0)
.venv/bin/python -m ml.train_damage_classifier --epochs 9
```

---

## The deep learning component is real

The damage classifier is genuinely trained, not a wrapper around a multimodal
API. EfficientNet-B0, two-phase transfer learning, on the public
[AIDER](https://doi.org/10.5281/zenodo.3888300) aerial disaster dataset
(6,433 images, CC-BY-4.0).

| Metric | Value |
| --- | --- |
| Validation accuracy | **90.6%** |
| Macro-F1 | **0.864** |
| Architecture | EfficientNet-B0, ImageNet-pretrained |
| Classes | flood · fire · collapsed building · blocked road · no damage |

**The error profile is deliberate.** The dataset is heavily imbalanced (4,390
"normal" images against ~500 per damage class). Unweighted training would score
~68% accuracy by simply never predicting damage. Inverse-frequency class
weighting plus macro-F1 model selection produced instead:

| Class | Recall |
| --- | --- |
| Flooded area | 96% |
| Collapsed building | 93% |
| Fire | 93% |
| Blocked road | 91% |
| Normal | 89% |

Residual error is concentrated in *normal → damage* false alarms. That is the
correct trade for disaster triage: a false alarm costs one wasted verification;
a missed collapse costs lives.

The CNN is one of three detectors. A vision-language model and an optional
YOLO detector sit behind the same interface, and the ensemble reports **model
agreement** — when detectors disagree the finding is flagged for human review
and its severity is downgraded rather than averaged into false confidence.

---

## Deterministic mode: the demo cannot fail

With no API key configured, SentinelAI does **not** break and does **not**
fabricate. Every agent carries a real deterministic fallback — actual domain
logic computing the same output type from the same tool evidence — and every
such output is marked `DEGRADED` in the API, the trace and the UI.

Offline, the platform is a rule-based expert system. Online, it is a reasoning
one. It is never a system pretending to reason.

Similarly, every external tool has an offline fallback, and **the fallbacks are
mutually consistent**: the offline weather model back-solves rainfall from the
seeded river-gauge dynamics, so the picture can never show clear skies beside a
river climbing 0.2 m/hour.

---

## Data integrity

Some deliberate constraints, because a disaster platform that misleads is worse
than none:

- **All registry data is synthetic and labelled as such.** Facility names use
  generic Indian public-health categories (District/Taluk Hospital, CHC) on real
  Kerala geography. Every seed file carries `_meta.synthetic: true`, and the UI
  shows a persistent `SIMULATED DATA` badge.
- **The knowledge base contains no fabricated quotations.** Each doctrine
  document is an openly-labelled original digest that paraphrases well-established
  public standards (Sphere minimums, START triage, ICS structure). None of it is
  passed off as the verbatim text of an NDMA or WHO publication.
- **The news tool generates no synthetic articles.** Every other fallback models
  physical dynamics honestly; fabricating headlines about real districts would
  manufacture disinformation — precisely what the Communication agent exists to
  counter. With no feed configured it returns zero articles and declares an
  explicit information gap.

---

## Architecture

```
backend/app/
  core/          config · structured logging · LLM factory · trace bus · resilience
  schemas/       Pydantic contracts — API surface, LLM output targets, graph state
  repositories/  geospatial registry queries
  tools/         capability-scoped tools, each with a disclosed fallback
  rag/           chunking · fastembed · Chroma · cited retrieval
  vision/        fine-tuned CNN + VLM + ensemble reconciliation
  memory/        episodic (per-incident) + semantic (cross-incident lessons)
  agents/        BaseAgent template method + 10 specialists
  graph/         LangGraph Pattern 5 assembly
  services/      allocation optimiser · orchestrator · scenarios
  api/           FastAPI routers + SSE
frontend/src/
  components/    AgentGraph · TacticalMap · TraceFeed · OperationalPanels
  hooks/         useIncidentRun — reduces the trace stream into live agent state
```

**Rules enforced throughout**

- Agents never call vendors. Agents call *tools*; tools call vendors.
- Tools run **before** the model, deterministically. Evidence gathering is not
  left to a model's discretion; judgement is.
- The optimiser computes quantities; the LLM explains them. `AllocationPlan` and
  `AllocationStrategy` are separate types so a model structurally cannot rewrite
  a number.
- Every node emits a trace. Observability is enforced by the base class, so an
  agent author cannot forget.

---

## Concepts demonstrated

| Concept | Where |
| --- | --- |
| Agentic AI / Multi-agent systems | 10 specialists under a Commander |
| LangGraph Pattern 5 | `graph/builder.py` — all four branch types |
| LangChain | tool adapters, chat models, structured output |
| ReAct + tool calling | `agents/base.py` gather → reason lifecycle |
| Prompt engineering | per-agent system prompts encoding real doctrine |
| Prompt chaining | `agents/knowledge.py` multi-query decomposition |
| Structured outputs | every agent returns a validated Pydantic type |
| Memory | `memory/store.py` — episodic + semantic lessons |
| Reflection | `agents/reflection.py` — a gate that genuinely rejects |
| RAG + embeddings + vector DB | `rag/` — fastembed + Chroma, cited retrieval |
| Deep learning / computer vision | `vision/` + `ml/` — trained EfficientNet-B0 |
| Predictive analytics | lead-time-to-danger, casualty projection, flood probability |

## UN SDGs

| SDG | Implementation |
| --- | --- |
| **3** Good Health | Medical agent: casualty distribution, bed deficit, ambulance planning, outbreak surveillance |
| **9** Infrastructure | Infrastructure agent: access corridors, structural risk, vision-based damage assessment |
| **11** Sustainable Cities | Shelter agent: Sphere minimum standards, flood-safe siting, vulnerable-group equity |
| **13** Climate Action | Weather agent: rainfall thresholds, river forecasting, early warning lead time |
| **17** Partnerships | Allocation across government, NDRF, municipal, hospital, NGO, fire service and volunteer depots |

---

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q      # 58 tests
```

Coverage focuses on what would actually mislead an operator: allocation
priority under scarcity, strategic-reserve preservation, honest shortfall
reporting, graph routing and cycle bounds, triage calibration regressions, and
tool fallback self-consistency.

---

## Attribution

Vision model trained on **AIDER** — Kyrkou & Theocharides, *Deep-Learning-Based
Aerial Image Classification for Emergency Response Applications Using Unmanned
Aerial Vehicles*, CVPR Workshops 2019. Licensed CC-BY-4.0.
