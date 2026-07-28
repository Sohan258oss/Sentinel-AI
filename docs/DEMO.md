# Demo Guide

A five-minute walkthrough that shows the architecture rather than describing it.

---

## Before you start

```bash
make setup          # once
make backend        # terminal 1
make frontend       # terminal 2  -> http://localhost:5173
```

The header pills show live subsystem state. `RULE-BASED` means no model key is
configured — the demo still works end to end, and that is itself worth showing.

---

## Act 1 — The flagship incident (90 seconds)

Click **Periyar River Flood — Aluva, Kerala**.

Watch the **agent graph** on the left, not the text. In order:

1. `IN` → `SA` light up — intake and triage.
2. `SA` runs the **vision ensemble** on a real flood photograph, plus weather
   and hydrology tools.
3. `CC` (Commander) lights, then **five specialist nodes light simultaneously**.
   That is the conditional fan-out executing as a single parallel superstep.
4. All five converge on `RA` (allocation).
5. `RF` (reflection) lights, then the **revise edge fires** and `RA` runs a
   second time.
6. `CM` (communication) closes the run.

Point at the **operations feed** on the right while this happens. Every tool
call, every retrieval, every critique is streamed live over SSE.

### What to say

> "The Commander decided which specialists this incident warranted. Nothing
> here is a fixed pipeline — that routing decision is made per incident."

---

## Act 2 — Prove the routing is real (45 seconds)

Click **Building Collapse — Kochi**, then open **ASSESSMENT** and scroll to
*Commander's Intent*.

Weather and Shelter appear under **declined**, with reasons. In the agent graph
those two nodes are struck through and never light.

### What to say

> "Same platform, different incident, genuinely different agent team. And when
> an agent is *not* activated, that decision is recorded with its reasoning —
> silent non-activation is indistinguishable from a bug."

---

## Act 3 — The reflection gate genuinely rejects (60 seconds)

Open the **ASSURANCE** tab on the flood incident.

Verdict: **REVISION REQUIRED**, with blocking findings — a 4,574-person shelter
capacity deficit, unmet rescue-boat and drinking-water requirements.

Now switch back to the building-collapse incident. Verdict: **APPROVED**, one
cycle, quality 88%.

### What to say

> "This is the part that is usually theatre. It isn't here — it approves sound
> plans and rejects unsound ones, and the rejection cites the specific deficit.
> The loop is bounded so a critical reviewer cannot burn tokens forever."

---

## Act 4 — Honest scarcity (45 seconds)

Open the **ALLOCATION** tab.

- Coverage **37%**, 217,471 units dispatched, **7 partner organisations**.
- A red **UNMET NEEDS** block: what is short, who is affected, the consequence,
  and exactly who to escalate to.

### What to say

> "Most demos show a plan that covers everything. Real districts don't have
> enough. The optimiser withholds a strategic reserve for the next incident,
> refuses to strip any single depot, and reports what it cannot cover —
> because escalation delayed is the most expensive error in disaster logistics."

---

## Act 5 — The deep learning is real (30 seconds)

Header pill reads **CNN 91%**.

```bash
curl -s localhost:8000/api/vision/status | python3 -m json.tool
```

Shows the confusion matrix and training metadata: EfficientNet-B0, 6,433
training images, 90.6% accuracy, 0.864 macro-F1.

### What to say

> "Trained, not prompted. The dataset is 68% 'normal', so unweighted training
> would score 68% by never predicting damage at all. Class-weighted loss and
> macro-F1 selection push damage recall to 91–96%, and the residual error is
> deliberately biased toward false alarms rather than misses."

---

## If asked: "what happens without an API key?"

That is the state it is already running in. Point at the amber banner.

> "Every agent has a real deterministic fallback — actual domain logic over the
> same tool evidence — and everything it produces is marked DEGRADED. Offline
> it's a rule-based expert system; online it's a reasoning one. It is never a
> system pretending to reason."

Then set `SENTINEL_GOOGLE_API_KEY` in `backend/.env`, restart, and run the same
scenario: the pill flips to `LLM LIVE`, the `DEGRADED` badges disappear, and the
narrative fields become genuine analysis.

---

## If asked: "is this data real?"

> "No, and it says so everywhere — that badge is permanent. The geography is
> real Kerala, the facility *categories* are real Indian public-health
> categories, the humanitarian standards are the real published minimums. The
> bed counts and stock levels are generated. We deliberately don't attribute
> invented capacity figures to named real hospitals, and the news tool returns
> zero articles rather than fabricating headlines about a real district."

---

## Fast terminal alternative

No browser needed:

```bash
make demo
```

Streams the same run as a live trace and prints the full operational picture.
