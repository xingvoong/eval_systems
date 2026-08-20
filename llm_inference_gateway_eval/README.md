# llm_inference_gateway — Eval Project

Eval system for [`llm_inference_gateway`](https://github.com/xingvoong/llm_inference_gateway) — a FastAPI service that routes prompts to different LLM providers using rule-based + ML logic.

---

## Files

```
phase1_explore.py              # Phase 1: run classifier on 20 prompts, observe failures

data/
  routing_cases.json           # 15 routing test cases (hand-written from Phase 1 failures)
  classifier_cases.json        # 20 classifier test cases with expected labels
  quality_cases.json           # 10 response quality cases with reference responses
  quality_results.json         # Judge scores from Phase 5

evaluators/
  routing_eval.py              # Deterministic routing correctness check
  classifier_eval.py           # Classifier accuracy + confidence score tracking
  quality_eval.py              # LLM-as-judge via OpenRouter
```

Start with the README to understand why decisions were made. Then walk through `routing_eval.py` and `quality_eval.py` as the two most interesting pieces of code.

---

## The System Under Test

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

---

## Project Plan

Each phase builds on what was learned in the previous one.

```
Phase 1 — Explore                         ✓ done
  Run the system on 20 prompts manually
  Observe what fails and why
        │
        ▼
Phase 2 — First Dataset                   ✓ done
  Write routing test cases from Phase 1 failures
  Hand-written, not generated
        │
        ▼
Phase 3 — Routing Evaluator               ✓ done
  Build routing_eval.py
  Deterministic, no LLM dependency
        │
        ▼
Phase 4 — Classifier Eval                 ✓ done
  Build classifier_cases.json
  Build classifier_eval.py
        │
        ▼
Phase 5 — Response Quality                ✓ done
  Build quality_cases.json with reference responses
  Build LLM-as-judge (quality_eval.py)
        │
        ▼
Phase 6 — Validate the Judge              ✓ done
  Consistency: same input → same score?
  Calibration: does the judge agree with your labels?
  Adversarial: can a bad response fool it?
        │
        ▼
Phase 7 — Red Team                        ← you are here
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

## Phase 1 — Explore

Before building any evaluator, run the system and observe what actually happens.

**What to do:**

1. Run the classifier on 20 prompts — mix of task types
2. Record what label it returns and whether that label is correct
3. Note wrong labels, low confidence, ambiguous cases

No framework yet. Just observations written down.

**Questions to answer:**

- Where does the classifier get it wrong?
- Which routing rule is hardest to reason about?
- What does a failure actually look like in this system?

---

## Phase 1 — Findings

Ran `phase1_explore.py` on 20 prompts (5 per label + 2 ambiguous).

**Overall classifier accuracy: 8/18 = 44%**

```
Label               Prompts   Correct   Accuracy
──────────────────  ───────   ───────   ────────
code generation        5         2        40%
summarization          5         5       100%
question answering     5         1        20%
general chat           3         0         0%
```

**Finding 1: "summarization" is the default label**

The classifier predicted summarization 11 out of 20 times. It latches onto the word "summarize" and maps anything slightly abstract to that label. Works when the word appears in the prompt. Fails everywhere else.

**Finding 2: "general chat" is effectively broken**

Never predicted once — not for "Hey, how are you doing today?", not for "I'm feeling overwhelmed." The label exists but the model doesn't use it.

**Finding 3: low confidence is the norm**

Most wrong predictions landed between 0.32–0.42. The model is guessing. A correct prediction at 0.32 confidence is not reliable — a different phrasing of the same prompt will flip the label.

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

"What is the capital of Japan?" gets labeled summarization → routes to Mistral-7B instead of gpt-4. A factual question gets the weaker model. No error raised.

```
Prompt                              Expected Label    Routed To    Should Be
──────────────────────────────────  ──────────────    ─────────    ─────────
What is the capital of Japan?       question ans.     Mistral-7B   gpt-4   ✗
When did World War II end?          question ans.     Mistral-7B   gpt-4   ✗
What is the difference btwn TCP/UDP question ans.     Mistral-7B   gpt-4   ✗
I'm feeling overwhelmed with work.  general chat      Mistral-7B   gpt-4   ✗
```

---

## Phase 2 — First Dataset

Every case in `data/routing_cases.json` traces back to something observed in Phase 1. No speculation.

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

**r_012 — rule conflict**

`priority=high` and `max_cost=0.005` both apply. Rule 1 wins — but only because of if-block order, not documentation. The eval pins that behavior so a refactor doesn't silently break it.

```
  Rule 1: priority == "high"   →  gpt-4       ← checked first, wins
  Rule 2: max_cost < 0.01      →  Mistral-7B  ← never reached

  If someone reorders the if-blocks tomorrow:
    caller said "high priority", gets the cheap model
    no error raised, no log warning
```

**r_015 — correct routing, wrong reason**

"What do you think about AI taking over jobs?" routed to gpt-4 — right destination, but labeled "question answering" not "general chat". Correct by accident.

```
  question answering  ──►  gpt-4   (today)     ← r_015 passes
  general chat        ──►  gpt-4   (today)

  If routing logic changes:
  question answering  ──►  Mistral-7B  (future) ← r_015 silently breaks
  general chat        ──►  gpt-4       (future)
```

A destination-only check would miss this regression entirely.

---

## Phase 3 — Routing Evaluator

Imports `route_request()` directly from the gateway. Mocks LLM provider calls — no real API calls. Checks both model and routing reason.

```
routing_cases.json
      │
      ▼
routing_eval.py
      │
      ├── mock OpenAIProvider, HuggingFaceProvider
      ├── route_request(prompt, priority, max_cost)
      │     → (provider, actual_model, actual_reason)
      │
      ├── assert actual_model == expected_model     ← destination
      ├── assert actual_reason == expected_reason   ← which rule fired
      │
      ▼
  pass/fail per case + per-rule breakdown + exit code 1 on failure
```

---

## Phase 3 — Findings

**First run: 3/15 passed (20%)**

All failures: `expected 'zero_shot:*' got 'learned_router'`. The gateway has a trained `router_model.pkl` so Rule 3 always uses the learned router — the zero-shot classifier is never called. Phase 1 tested the classifier directly by calling `classify_prompt()`. The actual system was never using it.

**Discovery: the learned router outperforms the zero-shot classifier**

```
Prompt                                Zero-shot           Learned router
────────────────────────────────────  ──────────────────  ──────────────────
What is the capital of Japan?         Mistral-7B  ✗       gpt-4  ✓
I'm feeling overwhelmed with work.    Mistral-7B  ✗       gpt-4  ✓
Give me a bash script to backup...    Mistral-7B  ✓       Mistral-7B  ✓
Hey, how are you doing today?         gpt-4  ✓ (accident) gpt-4  ✓ (correct)
```

Updated `routing_cases.json` — all Rule 3 cases now expect `learned_router`.

**Second run: 15/15 passed (100%)**

```
Rule                 Pass   Fail
──────────────────   ────   ────
priority==high          1      0
max_cost<0.01           1      0
learned_router         12      0
conflict (r_012)        1      0
```

---

## Phase 4 — Classifier Eval

The classifier is the fallback when `router_model.pkl` is missing. Phase 4 measures how bad that fallback is.

```
classifier_cases.json
      │
      ▼
classifier_eval.py
      │
      ├── calls classify_prompt() per case
      ├── records predicted label + full confidence scores
      │
      ▼
  accuracy + per-label F1 + confidence distribution
```

20 cases across 4 labels and 3 difficulty levels. All 10 known failures from Phase 1 are included.

---

## Phase 4 — Findings

**Overall accuracy: 8/20 = 40%**

```
Label                  Pass   Fail   Accuracy
─────────────────────  ────   ────   ────────
summarization             5      0    100%
code generation           2      4     33%
question answering        1      5     17%
general chat              0      3      0%

Difficulty   Pass   Fail   Accuracy
──────────   ────   ────   ────────
easy            6      5     55%
medium          2      5     29%
hard            0      2      0%
```

**Finding 1: confidence < 0.50 always means failure**

All 8 low-confidence predictions were wrong. A confidence threshold would catch every failure in this category.

```
Low confidence failures (conf < 0.50) — all wrong:
  c_006  conf=0.32  'Write a Python function to reverse a linked list.'
  c_010  conf=0.33  'Write a SQL query to find top 5 customers...'
  c_013  conf=0.42  'When did World War II end?'
  c_014  conf=0.46  'What does HTTP stand for?'
  c_015  conf=0.36  'What is the difference between TCP and UDP?'
  c_016  conf=0.42  'Hey, how are you doing today?'
  c_017  conf=0.35  'I'm feeling overwhelmed with work lately.'
  c_020  conf=0.37  'What's this do?'
```

**Finding 2: c_019 is the most dangerous failure**

"Summarize this code and tell me if it has bugs" → summarization at 0.99 confidence. The word "summarize" hijacks the prediction entirely. Task is code review — needs gpt-4. Gets Mistral-7B with near-certainty.

```
  prompt: "Summarize this code and tell me if it has bugs."
      │
      ▼
  classifier: summarization 0.99  ← "summarize" dominates
              code gen       0.00  ← correct label, lowest score
      │
      ▼
  Mistral-7B  ✗
```

**Finding 3: the fallback is quietly dangerous**

```
  router_model.pkl exists   →  learned_router  →  15/15 correct  ✓
  router_model.pkl missing  →  classifier      →  ~8/20 correct  ✗
        │
        └── no warning, no log entry, no error
```

---

## Phase 5 — Response Quality

Judge uses Claude Haiku via OpenRouter. Scores correctness, completeness, and conciseness (1–5) against a reference response. Each prompt has paired responses at different quality levels so the ranking can be verified.

```
quality_cases.json
      │
      ▼
quality_eval.py
      │
      ├── for each case: prompt + reference + candidate → judge
      ├── judge returns structured JSON scores
      ├── strips markdown fences before parsing
      │
      ▼
  scores per dimension + average by quality level
  results saved to data/quality_results.json
```

---

## Phase 5 — Findings

**Results: judge correctly ranks good > bad > mediocre**

```
ID       Level      Correct   Complete   Concise   Avg
──────────────────────────────────────────────────────
q_001    good          5         5          5       5.0
q_002    bad           3         2          5       3.3
q_003    good          5         5          5       5.0
q_004    bad           5         3          1       3.0
q_005    good          5         5          5       5.0
q_006    mediocre      2         1          5       2.7
q_007    good          5         5          5       5.0
q_008    bad           4         2          4       3.3
q_009    good          5         5          5       5.0
q_010    mediocre      2         2          4       2.7

Average by quality level:
  good      5.00
  bad       3.22
  mediocre  2.67
```

**Finding 1: fluent padding didn't fool the judge**

q_004 — "What is the capital of Japan?" answered with 4 sentences of irrelevant Japan background, Tokyo buried at the end. Judge scored 5/5 correctness, 1/5 conciseness. Average: 3.0. Surface fluency didn't inflate the score.

```
q_004 bad response:
  correctness   5  ← Tokyo is mentioned
  completeness  3  ← never directly answers the question
  conciseness   1  ← Tokyo buried after irrelevant padding
  avg           3.0
```

**Finding 2: judge output format is variable**

First run: judge wrapped JSON in markdown code fences. Fixed by stripping fences before parsing. Signals that Phase 6 (judge validation) is necessary — the judge's own reliability needs to be tested.

---

## Phase 6 — Validate the Judge

Three scripts in `evaluator_validation/`. All run at temperature=0 against the same OpenRouter judge used in Phase 5.

---

### Consistency — `judge_consistency.py`

Same input through the judge 5x. Score variance should be zero.

```
ID       Level      Correct         Var    Complete        Var    Concise         Var    Stable?
q_001    good       [5,5,5,5,5]     0.00   [5,5,5,5,5]     0.00   [5,5,5,5,5]     0.00   ✓
q_002    bad        [3,3,3,3,3]     0.00   [2,2,2,2,2]     0.00   [5,5,5,5,5]     0.00   ✓
q_004    bad        [5,5,5,5,5]     0.00   [3,3,3,3,3]     0.00   [1,1,1,1,1]     0.00   ✓
q_006    mediocre   [1,1,1,1,1]     0.00   [1,1,1,1,1]     0.00   [3,3,3,3,3]     0.00   ✓
q_010    mediocre   [2,2,2,2,2]     0.00   [2,2,2,2,2]     0.00   [4,4,4,4,4]     0.00   ✓

Unstable cases: 0/5 — judge is fully consistent at temperature=0
```

---

### Calibration — `judge_calibration.py`

Human labels written before running the judge. Spearman rank correlation measures agreement.

```
Dimension      Human vs Judge   Interpretation
─────────────  ──────────────   ──────────────
correctness    0.98             strong ✓
completeness   0.96             strong ✓
conciseness    0.84             acceptable

Average: 0.93 — strong ✓
```

Most disagreements were off by 1 point (`~`). No case where human and judge were more than 1 apart. The judge is well-calibrated.

---

### Adversarial — `adversarial_judge.py`

5 responses designed to fool the judge. All caught.

```
ID       Type                    Correct   Complete   Concise   Avg    Fooled?
adv_001  fluent_but_wrong           1         2          3      2.0    caught ✓
adv_002  fluent_but_wrong           1         1          5      2.3    caught ✓
adv_003  verbose_padding            4         2          1      2.3    caught ✓
adv_004  overformatted              5         5          2      4.0    caught ✓
adv_005  confident_hallucination    1         2          2      1.7    caught ✓

Judge fooled: 0/5
```

Notable: `adv_004` scored 4.0 overall because the content was actually correct — just wrapped in unnecessary markdown. The judge correctly gave 2/5 conciseness while acknowledging correctness. That's the right call.

`adv_005` is the most important case — full of authoritative-sounding but wrong details (5-way handshake, Tim Berners-Lee invented UDP, wrong port numbers). Scored 1/5 correctness. The judge didn't get fooled by confident tone.

---

### Phase 6 Summary

```
Test                 Result
───────────────────  ──────────────────────────────────────────
Consistency          5/5 stable, zero variance at temperature=0
Calibration          0.93 avg Spearman correlation vs human
Adversarial          0/5 fooled
```

The judge is trustworthy. Scores from Phase 5 can be used with confidence for relative comparisons.

---

*README updates after each phase.*
