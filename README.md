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
| [synack-agent-prep](./synack_agent_prep_eval/) | Multi-module CVE research agent with guardrails and multi-agent orchestration | In progress (5/7 phases) |

### synack-agent-prep — Phase Progress

| Phase | What | Result |
|---|---|---|
| 1 — Guardrail Eval | Input blocking, output scanning | 19/20 — 1 regex gap found |
| 2 — Tool Routing Eval | run_tool() dispatch, NVD parsing (mocked HTTP) | 9/9 |
| 3 — Degradation Eval | Worker timeout → partial result, not crash | 4/4 |
| 4 — Response Quality | LLM-as-judge: CVE answers accurate and grounded? | good 5.0, bad 3.6, mediocre 1.5 |
| 5 — Judge Validation | Consistency, calibration, adversarial | 0.86 Spearman, 1/5 fooled |
| 6 — Red Team | Injection bypass attempts | — |
| 7 — CI | run_evals.sh + GitHub Actions | — |

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

## Course → AIUC Mapping

| Course Topic | AIUC-1 Domain |
|---|---|
| Agent instrumentation & tracing | Accountability |
| Error analysis & failure modes | Reliability |
| LLM-as-judge evaluators | How AIUC-1 audits work |
| Evaluator validation | Certification credibility |
| Safety red-teaming | Security + Safety |
| CI/CD integration | Continuous certification |
