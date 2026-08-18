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

## Project Plan

Each phase builds on what was learned in the previous one. README updates at the end of each phase.

```
Phase 1 — Explore                         ✓ done
  Run the system manually on 20 prompts
  Observe what fails and why
  No code, just notes
        │
        ▼
Phase 2 — First Dataset                   ← you are here
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

*README updates after each phase.*
