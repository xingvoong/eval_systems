# eval_systems

A collection of eval projects for AI systems I've built. Each project evaluates a different system end to end — routing correctness, response quality, adversarial robustness.

Built alongside the [AI Evals For Engineers & PMs](https://maven.com/parlance-labs/evals) course, with a focus on interview prep for [AIUC](https://aiuc.com) — an AI agent certification and insurance company.

---

## Why Evals

AIUC certifies AI agents against their AIUC-1 standard. Their product *is* an eval system. Every project here maps to one or more of the six AIUC-1 domains:

| AIUC-1 Domain | What It Checks |
|---|---|
| Reliability | Does the system behave consistently? |
| Accountability | Can you trace why a decision was made? |
| Security | Prompt injection, adversarial inputs, boundary attacks |
| Safety | Does the system refuse harmful outputs? |
| Data & Privacy | How does it handle sensitive inputs? |
| Societal Risks | Bias, misuse potential |

---

## Systems Under Eval

| Project | What It Is | Status |
|---|---|---|
| [llm_inference_gateway](./llm_inference_gateway_eval/) | FastAPI service that routes prompts to LLM providers | Complete (8/8 phases) |
| [synack-agent-prep](./synack_agent_prep_eval/) | Multi-module CVE research agent with guardrails and multi-agent orchestration | Complete (7/7 phases) |

### synack-agent-prep — Phase Progress

| Phase | What | Result |
|---|---|---|
| 1 — Guardrail Eval | Input blocking, output scanning | 19/20 — 1 regex gap found |
| 2 — Tool Routing Eval | run_tool() dispatch, NVD parsing (mocked HTTP) | 9/9 |
| 3 — Degradation Eval | Worker timeout → partial result, not crash | 4/4 |
| 4 — Response Quality | LLM-as-judge: CVE answers accurate and grounded? | good 5.0, bad 3.6, mediocre 1.5 |
| 5 — Judge Validation | Consistency, calibration, adversarial | 0.86 Spearman, 1/5 fooled |
| 6 — Red Team | Injection bypass attempts | Input 5/13, output 1/4 — encoding/evasion bypasses documented |
| 7 — CI | run_evals.sh + GitHub Actions | 5/5 PASS, 1 SKIP (no API key in CI) |

---

### llm_inference_gateway — Phase Progress

| Phase | What | Result |
|---|---|---|
| 1 — Explore | Run classifier on 20 prompts, observe failures | 44% accuracy, "general chat" never predicted |
| 2 — Dataset | Hand-write routing + classifier test cases | 15 routing, 20 classifier, 10 quality cases |
| 3 — Routing Eval | Deterministic routing correctness | 15/15 after fixing Rule 3 expectations |
| 4 — Classifier Eval | Accuracy + confidence per label | 65% overall; "question answering" 40%, "general chat" 20% |
| 5 — Response Quality | LLM-as-judge via OpenRouter | Good responses avg 4.6, bad responses avg 1.7 |
| 6 — Judge Validation | Consistency, calibration, adversarial | 0 variance, 0.93 Spearman correlation, 0/5 fooled |
| 7 — Red Team | Adversarial routing + classifier attacks | Routing 12/12 held; classifier 3/6 held (50%) |
| 8 — CI | `run_evals.sh` + GitHub Actions | 4/4 PASS, 1 SKIP (no API key in CI) |

---

## Shared Patterns

Every eval project in this repo follows the same structure:

```
<system>_eval/
├── data/               # Labeled test cases (hand-written)
├── evaluators/         # Code-based + LLM-as-judge
├── evaluator_validation/  # Proving the judge works
├── red_team/           # Adversarial inputs
├── tracing/            # Log parsing and observability
└── ci/                 # Threshold checks + report generation
```

---

## What Matters When Evaluating a System

After two projects, the pattern is clear. Every system has the same layers, and each layer needs a different kind of eval.

**1. Deterministic behavior first.**

Routing rules, guardrails, dispatch logic, degradation paths. These have right answers. Write labeled cases, run code-based evals, enforce thresholds in CI. If you can't get 100% on deterministic logic, the probabilistic stuff on top doesn't matter.

**2. LLM behavior second — but validate the judge before trusting it.**

Once you need an LLM to evaluate an LLM, you've added a second model to your error budget. Run consistency checks (zero variance at temperature=0 is the bar), calibrate against human labels (Spearman > 0.85), and probe it with adversarial inputs. A judge that rewards fluency is worse than no judge — it gives you false confidence.

**3. Red team after you know what works.**

Adversarial testing without a baseline is noise. Run the happy path first, document what holds, then systematically attack the boundaries. The goal is to find the failure mode, not to maximize the broke count.

**4. CI locks in the baseline.**

Thresholds should be set to the observed result, not an aspirational target. A threshold you can't currently hit is a broken build, not a goal. What CI actually catches is regression — a future code change that silently breaks something you already verified.

---

## Eval Architecture — Scaling to More Systems

The same eval pipeline works for any system. Add a new `<system>_eval/` directory and wire it into the shared CI job.

```
eval_systems/
│
├── llm_inference_gateway_eval/     ← System A
│   ├── data/                       labeled cases
│   ├── evaluators/                 code-based + LLM-as-judge
│   ├── evaluator_validation/       judge consistency, calibration, adversarial
│   ├── red_team/                   adversarial inputs
│   └── ci/                         run_evals.sh + requirements.txt
│
├── synack_agent_prep_eval/         ← System B
│   ├── data/
│   ├── evaluators/
│   ├── evaluator_validation/
│   ├── red_team/
│   └── ci/
│
├── <next_system>_eval/             ← System C (same structure)
│   ├── data/
│   ├── evaluators/
│   ├── evaluator_validation/
│   ├── red_team/
│   └── ci/
│
└── .github/workflows/evals.yml     ← one job per system, runs in parallel
```

Each system eval is self-contained. The GitHub Actions workflow runs them as parallel jobs — a failure in one doesn't block the others. Adding a new system is: copy the structure, write the cases, add a job to the workflow.

```
.github/workflows/evals.yml

jobs:
  llm-gateway-evals:       ← System A job
    steps: [checkout A, install deps, run ci/run_evals.sh]

  synack-agent-evals:      ← System B job
    steps: [checkout B, install deps, run ci/run_evals.sh]

  <next-system>-evals:     ← System C job (same pattern)
    steps: [checkout C, install deps, run ci/run_evals.sh]
```

The shared contract across all systems: `ci/run_evals.sh` exits 0 on pass, 1 on failure. The workflow treats any non-zero exit as a failing check. That's the only interface the CI layer cares about.

---

## Course → AIUC Mapping

| Course Topic | AIUC-1 Domain |
|---|---|
| Agent instrumentation & tracing | Accountability |
| Error analysis & failure modes | Reliability |
| LLM-as-judge evaluators | How AIUC-1 audits work |
| Evaluator validation | Certification credibility |
| Safety red-teaming | Security + Safety |
| CI/CD integration | Continuous certification |

---

## Takeaways

**Hand-write your test cases before you run anything.**

Both projects started with labeled datasets written before the first eval ran. That discipline paid off in judge calibration — human labels written without seeing judge scores are the only clean signal. If you label after the fact, you're fitting to the judge, not measuring it.

**The classifier is always the weakest link.**

Deterministic routing held 100% on both red teams. The zero-shot classifier failed on low-frequency labels ("general chat" at 20%, "question answering" at 40%) and cracked under lexical overlap attacks (3/6 held). Routing logic is testable and stable. Classification is a model problem — it doesn't hold under distribution shift.

**An LLM judge that agrees with humans 0.9 Spearman is still wrong on the cases that matter.**

Both judges scored high on calibration. Both rewarded fluency on bad responses. Completeness scores were near-identical for correct and incorrect answers as long as the response was well-structured. Accuracy is the only dimension worth trusting. The other dimensions measure how the answer *looks*, not whether it's *right*.

**Adversarial evasion is cheap. Defense is not.**

Regex guardrails broke on zero-width spaces, unicode homoglyphs, double spaces, and leetspeak. Every bypass was one character substitution. A normalized input pipeline (unicode NFKC + whitespace collapse) would close most of these gaps, but none of the systems under eval had one. Pattern matching without normalization is security theater against anyone who has read the source.

**Evals find the gap between what the code does and what it should do.**

Not bugs — gaps. The regex was correct. The routing logic was correct. The judge was consistent. The gaps were in the specification: a pattern that matched one modifier word but not two, a completeness metric that couldn't distinguish correct from incorrect, a classifier that had never seen its own low-frequency labels. You don't find those by reading the code. You find them by running the eval.
