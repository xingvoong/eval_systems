# llm_inference_gateway — Eval Project

Eval system for [`llm_inference_gateway`](https://github.com/xingvoong/llm_inference_gateway) — a FastAPI service that routes prompts to different LLM providers using rule-based + ML logic.

---

## Phase 1 — Explore

Before building any evaluator, run the system and observe what actually happens.

**The system under test:**

```
┌─────────────────────────────────────────────────────────┐
│                  llm_inference_gateway                   │
│                                                         │
│   POST /chat                                            │
│   { prompt, priority, max_cost }                        │
│          │                                              │
│          ▼                                              │
│   ┌─────────────┐                                       │
│   │   router.py │                                       │
│   └──────┬──────┘                                       │
│          │                                              │
│   Rule 1: priority == "high"  ──────────────► gpt-4    │
│          │                                              │
│   Rule 2: max_cost < 0.01  ─────────────► Mistral-7B   │
│          │                                              │
│   Rule 3: learned model exists?                         │
│          ├── yes ──► learned_router.py ──► model        │
│          └── no  ──► classifier.py                      │
│                          │                              │
│                   ┌──────┴──────┐                       │
│                   │             │                       │
│              code gen      general chat                 │
│            summarization   question answering           │
│                   │             │                       │
│              Mistral-7B       gpt-4                     │
│                                                         │
│   Every request: log(prompt, model, reason, latency)    │
│   Cache: hit → skip LLM call, return cached response    │
└─────────────────────────────────────────────────────────┘
```

**What to do:**

1. Run the classifier on 20 prompts manually — mix of task types
2. Record what label it returns and whether that label is correct
3. Note any surprises: wrong labels, low confidence, ambiguous cases
4. Do the same for routing — does the right model get picked?

No framework yet. Just observations written down.

**Questions to answer by the end of Phase 1:**

- Where does the classifier get it wrong?
- Which routing rule is hardest to reason about?
- What does a failure actually look like in this system?

---

## Project Plan

Each phase builds on what was learned in the previous one. README updates at the end of each phase.

```
Phase 1 — Explore                         ← you are here
  Run the system manually on 20 prompts
  Observe what fails and why
  No code, just notes
        │
        ▼
Phase 2 — First Dataset
  Write 10-15 routing test cases
  Based on real failures from Phase 1
  Hand-written, not generated
        │
        ▼
Phase 3 — First Evaluator
  Build routing_eval.py
  Deterministic, no LLM dependency
  Get it green
        │
        ▼
Phase 4 — Classifier Eval
  Build classifier_cases.json
  Build classifier_eval.py
  Track accuracy + confidence scores
        │
        ▼
Phase 5 — Response Quality
  Build quality_cases.json with reference responses
  Build LLM-as-judge (quality_eval.py)
        │
        ▼
Phase 6 — Validate the Judge
  Consistency: same input → same score?
  Calibration: does the judge agree with your labels?
  Adversarial: can a bad response fool it?
        │
        ▼
Phase 7 — Red Team
  Adversarial routing inputs
  Adversarial classifier inputs
        │
        ▼
Phase 8 — CI
  Wire everything into run_evals.sh
  Set pass/fail thresholds
  GitHub Actions
```

---

*README updates after Phase 1 is done.*
