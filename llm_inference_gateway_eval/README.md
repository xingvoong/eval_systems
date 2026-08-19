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
│          │  (caller says: use best model, ignore cost)  │
│          │                                              │
│   Rule 2: max_cost < 0.01  ─────────────► Mistral-7B   │
│          │  (caller says: stay cheap, skip classifier)  │
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

## Phase 1 — Findings

Ran `phase1_explore.py` on 20 prompts (5 per label + 2 ambiguous).

**Overall classifier accuracy: 8/18 = 44%**

The classifier is wrong more than half the time.

```
Label               Prompts   Correct   Accuracy
──────────────────  ───────   ───────   ────────
code generation        5         2        40%
summarization          5         5       100%
question answering     5         1        20%
general chat           3         0         0%
```

**Finding 1: "summarization" is the default label**

The classifier predicted summarization 11 out of 20 times. It latches onto the word "summarize" in training data and maps anything slightly abstract to that label. Works great when the word appears in the prompt. Fails everywhere else.

**Finding 2: "general chat" is effectively broken**

The classifier never once predicted "general chat" as the top label. Not for "Hey, how are you doing today?", not for "I'm feeling overwhelmed with work." The label exists but the model doesn't use it.

**Finding 3: low confidence is the norm, not the exception**

Most wrong predictions landed between 0.32–0.42 confidence. The model is guessing. A correct prediction at 0.32 (prompt #1 — "Write a Python function...") is not reliable. A different phrasing of the same prompt will flip the label.

```
Prompt                                    Predicted      Confidence
────────────────────────────────────────  ─────────────  ──────────
Write a Python function to reverse a...  summarization     0.32   ✗
What is the capital of Japan?            summarization     0.71   ✗  ← confident and wrong
What does HTTP stand for?                code generation   0.46   ✗
When did World War II end?               summarization     0.42   ✗
Hey, how are you doing today?            question ans.     0.42   ✗
```

**Finding 4: wrong labels cause silent routing failures**

The routing consequence of a wrong label isn't visible in the logs — you just see the wrong model got picked. "What is the capital of Japan?" gets labeled summarization → routes to Mistral-7B instead of GPT-4. A factual question gets the weaker model. No error raised.

```
Prompt                              Expected Label      Routed To    Should Be
──────────────────────────────────  ──────────────      ─────────    ─────────
What is the capital of Japan?       question ans.       Mistral-7B   gpt-4   ✗
When did World War II end?          question ans.       Mistral-7B   gpt-4   ✗
What is the difference btwn TCP/UDP question ans.       Mistral-7B   gpt-4   ✗
I'm feeling overwhelmed with work.  general chat        Mistral-7B   gpt-4   ✗
```

**What this means for Phase 2**

The classifier is the weakest part of the system. The rule-based routing (Rule 1 and Rule 2) works fine — those are deterministic. The problem is Rule 3, which depends entirely on a classifier that is unreliable for 3 of 4 labels.

The dataset in Phase 2 should focus on the failure modes observed here: question answering mislabeled as summarization, general chat never predicted, and low-confidence code generation.

---

## Phase 2 — First Dataset

Every case in `data/routing_cases.json` traces back to something observed in Phase 1. No speculation.

**Why not just write 40 cases covering everything equally?**

Because Phase 1 showed the real problem is concentrated in 3 of 4 labels. Distributing cases evenly would have hidden that — summarization successes would have offset the failures and made the overall accuracy look better than it is.

**15 cases, organized by what Phase 1 revealed:**

```
Cases       What they cover
──────────  ───────────────────────────────────────────────────────
r_001–003   QA mislabeled as summarization → wrong model (silent)
r_004–005   General chat never predicted → wrong model
r_006–007   Code gen mislabeled as summarization
r_008–009   Summarization baseline — classifier works here
r_010–011   Rule 1 and Rule 2 baselines (deterministic)
r_012       Rule 1 vs Rule 2 conflict — priority=high wins
r_013       Technical QA drifts toward code gen label
r_014       Ambiguous case — flagged for review
r_015       General chat routed correctly by accident (wrong label)
```

`r_012` is the most interesting case — `priority=high` and `max_cost=0.005` both apply. Rule 1 wins. This is undefined behavior in the codebase (no explicit conflict resolution), but the code happens to check `priority` first. Worth testing explicitly.

```
r_012 — { prompt: "What is the capital of Japan?", priority: "high", max_cost: 0.005 }

Both rules fire on this request:

  Rule 1: priority == "high"   →  gpt-4       (use best model, ignore cost)
  Rule 2: max_cost < 0.01      →  Mistral-7B  (stay cheap, skip classifier)
       │
       │  conflict — which rule wins?
       ▼

How router.py resolves it (implicitly):

  def route_request(prompt, priority, max_cost):
      if priority == "high":          ← checked first → Rule 1 wins
          return gpt-4
      if max_cost < 0.01:             ← never reached
          return Mistral-7B

  Result: gpt-4   ✓


Why this is worth an explicit test case:

  Today              priority=high → gpt-4    (Rule 1 wins by code order)
       │
       │  someone reorders the if-blocks
       ▼
  Tomorrow           max_cost<0.01 → Mistral-7B  (Rule 2 now wins)
                          │
                          └── caller said "high priority", gets cheap model
                              no error raised, no log warning
```

The conflict resolution is not documented anywhere in the codebase. It works by accident of if-block order. The eval pins that behavior so any reordering gets caught.

`r_015` is a reminder that correct routing and correct label are not the same thing. "What do you think about AI taking over jobs?" routed to gpt-4 — right destination, but because the classifier called it "question answering", not "general chat". The routing was correct for the wrong reason.

```
r_015 — "What do you think about AI taking over jobs?"

What actually happened:
  prompt
    │
    ▼
  classifier
    │
    └── predicted: question answering (0.66)   ← WRONG label
                        │
                        ▼
                      gpt-4                    ← correct destination (by accident)


What should have happened:
  prompt
    │
    ▼
  classifier
    │
    └── predicted: general chat               ← correct label
                        │
                        ▼
                      gpt-4                   ← correct destination


Why this is dangerous — if routing logic ever changes:
  question answering  ──►  gpt-4        (today)
  general chat        ──►  gpt-4        (today)
       │
       │  routing rule changes
       ▼
  question answering  ──►  Mistral-7B   (future)
  general chat        ──►  gpt-4        (future)
       │
       └──  r_015 silently breaks — no error raised, wrong model used
```

A destination-only check would mark this as a pass today and miss the regression tomorrow.

---

## Phase 3 — First Evaluator

Build a deterministic evaluator that runs each routing case through the actual gateway logic. No LLM calls, no network requests — just routing decisions.

**Design decisions:**

- Import `route_request()` directly from the gateway — test the real code, not a copy
- Mock `OpenAIProvider` and `HuggingFaceProvider` — we're testing routing, not responses
- Check both `model` and `routing_reason` — destination alone isn't enough (see r_015)
- Report per-rule breakdown, not just overall accuracy

```
routing_cases.json
      │
      ▼
routing_eval.py
      │
      ├── sys.path.insert → gateway repo
      ├── mock OpenAIProvider, HuggingFaceProvider
      │
      ├── for each case:
      │     route_request(prompt, priority, max_cost)
      │           │
      │     returns (provider, actual_model, actual_reason)
      │           │
      │     assert actual_model == expected_model        ← destination
      │     assert actual_reason == expected_reason      ← which rule fired
      │
      ▼
Output:
  • Pass/fail per case
  • Failure reason (model mismatch, reason mismatch, or both)
  • Per-rule breakdown
  • Exit code 1 if any case fails  ← CI-ready
```

**What to do:**

1. Write `evaluators/routing_eval.py`
2. Run it — expect failures on first pass
3. Diagnose failures, fix the dataset or the script
4. Get it green

---

## Phase 3 — Findings

Built `evaluators/routing_eval.py`. Imports `route_request()` directly from the gateway, mocks LLM provider calls, runs all 15 cases.

**First run: 3/15 passed (20%)**

All failures had the same reason: `expected 'zero_shot:*' got 'learned_router'`. The gateway has a trained `router_model.pkl`, so `is_trained_model_available()` returns True and Rule 3 always uses the learned router — not the zero-shot classifier.

Phase 1 tested the classifier in isolation by calling `classify_prompt()` directly. The actual system was never using it. The dataset was written against the wrong path.

**Discovery: the learned router is better than the zero-shot classifier**

```
Prompt                                  Zero-shot result     Learned router result
──────────────────────────────────────  ───────────────────  ─────────────────────
What is the capital of Japan?           Mistral-7B  ✗        gpt-4  ✓
I'm feeling overwhelmed with work.      Mistral-7B  ✗        gpt-4  ✓
Give me a bash script to backup files   Mistral-7B  ✓        Mistral-7B  ✓
Hey, how are you doing today?           gpt-4  ✓ (accident)  gpt-4  ✓ (correct)
```

Updated `routing_cases.json` to reflect reality — all Rule 3 cases now expect `learned_router`.

**Second run: 15/15 passed (100%)**

```
Rule                 Pass   Fail
──────────────────   ────   ────
priority==high          1      0
max_cost<0.01           1      0
learned_router         12      0
conflict (r_012)        1      0
```

The evaluator is green. Rule-based routing works. The learned router routes all test cases correctly.

---

## Project Plan

Each phase builds on what was learned in the previous one. README updates at the end of each phase.

```
Phase 1 — Explore                         ✓ done
  Run the system manually on 20 prompts
  Observe what fails and why
  No code, just notes
        │
        ▼
Phase 2 — First Dataset                   ✓ done
  Write 10-15 routing test cases
  Based on real failures from Phase 1
  Hand-written, not generated
        │
        ▼
Phase 3 — First Evaluator                 ✓ done
  Build routing_eval.py
  Deterministic, no LLM dependency
  Get it green
        │
        ▼
Phase 4 — Classifier Eval                 ← you are here
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

*README updates after each phase.*
