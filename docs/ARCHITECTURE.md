# SentinelAI — Architecture

> Autonomous Multi-Agent Disaster Intelligence & Resilience Platform
> **Predict. Coordinate. Respond. Recover.**

---

## 1. Design thesis

Most disaster-tech is a *notification system with a database behind it*. SentinelAI is
built as an **Emergency Operations Center staffed by AI officers**. The distinction is
architectural, not cosmetic:

| Conventional system | SentinelAI |
| --- | --- |
| User asks, system answers | Incident arrives, system *deploys* an agent team |
| One model, one prompt | Commander delegates to specialist agents in parallel |
| Static rules | Conditional routing decided per-incident by an LLM planner |
| Answer is final | Reflection agent critiques and forces revision |
| "Here is information" | "Here is the allocation plan, and why" |

Everything the operator sees is the **byproduct of an agent run**, streamed live.

---

## 2. The flow pattern — Pattern 5: Hybrid LangGraph Branching

The workbook mandates Pattern 5. We implement all three of its constituent
behaviours in a single graph, rather than a linear chain wearing a graph's clothes:

```
                          ┌──────────────┐
   incident report  ──▶   │   INTAKE     │  normalize + geocode + attach media
                          └──────┬───────┘
                                 ▼
                          ┌──────────────┐
                          │  SITUATION   │  ReAct + vision + structured triage
                          │   ANALYSIS   │
                          └──────┬───────┘
                                 ▼
                          ┌──────────────┐
                          │  COMMANDER   │  ◀── ①  CONDITIONAL ROUTING
                          │   (planner)  │      LLM emits an activation plan:
                          └──────┬───────┘      which specialists are warranted?
                                 │
        ┌──────────┬─────────────┼─────────────┬──────────┐   ②  PARALLEL FAN-OUT
        ▼          ▼             ▼             ▼          ▼
   ┌────────┐ ┌─────────┐ ┌────────────┐ ┌────────┐ ┌──────────┐
   │WEATHER │ │ MEDICAL │ │INFRASTRUCT.│ │SHELTER │ │KNOWLEDGE │
   │ agent  │ │  agent  │ │   agent    │ │ agent  │ │ (RAG)    │
   └────┬───┘ └────┬────┘ └─────┬──────┘ └───┬────┘ └────┬─────┘
        └──────────┴─────────────┼───────────┴───────────┘
                                 ▼                            ③  FAN-IN / JOIN
                          ┌──────────────┐
                          │  ALLOCATION  │  constrained optimiser + LLM rationale
                          └──────┬───────┘
                                 ▼
                          ┌──────────────┐
                          │  REFLECTION  │ ──── critique ────┐   ④  CYCLE
                          └──────┬───────┘                   │
                                 │ approved            revise│
                                 ▼                           │
                          ┌──────────────┐                   │
                          │COMMUNICATION │ ◀─────────────────┘
                          └──────────────┘
```

① conditional edges ② parallel superstep ③ reducer-based join ④ bounded cyclic
revision. That is a *hybrid* branching graph, not a pipeline.

---

## 3. Layering

```
app/
  core/       config, logging, LLM factory, resilience primitives
  schemas/    Pydantic contracts — the type system of the whole product
  tools/      LangChain tools, one registry, capability-scoped per agent
  rag/        ingestion → chunking → embedding → Chroma → cited retrieval
  vision/     fine-tuned CNN + YOLO detector + VLM ensemble, one interface
  memory/     episodic (per-incident) + semantic (cross-incident lessons)
  agents/     specialist agents, all subclasses of one BaseAgent
  graph/      the LangGraph assembly — nodes, edges, routing, checkpointing
  services/   orchestration façade consumed by the API
  api/        FastAPI routers + SSE trace stream
```

**Rule enforced throughout:** agents never talk to vendors. Agents call *tools*;
tools call vendors; every vendor has a deterministic offline fallback so a demo
can never die on a missing API key or a rate limit.

---

## 4. Observability as a feature

Every node emits an `AgentTrace` event onto an async bus. The frontend subscribes
over SSE and renders the graph lighting up in real time — reasoning, tool calls,
citations, confidence, latency. The "wow" of the demo *is* the observability layer.

---

## 5. SDG mapping

| SDG | Where it lives in the code |
| --- | --- |
| 3 — Health | `agents/medical.py`, hospital & ambulance tools |
| 9 — Infrastructure | `agents/infrastructure.py`, vision damage model |
| 11 — Cities | `agents/shelter.py`, allocation optimiser |
| 13 — Climate | `agents/weather.py`, flood/river forecasting |
| 17 — Partnerships | multi-org resource registry, `agents/volunteer.py` |
