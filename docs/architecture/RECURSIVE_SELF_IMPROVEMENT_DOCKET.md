# Recursive Self-Improvement Court Docket

## Sources and custody

| Source | Docket ID | Status | Use |
|---|---|---|---|
| `https://www.youtube.com/watch?v=t7_ZXgfJVG8` — *Recursive Self Improvement*, Emergent Garden | `SRC-020` | Partial ingestion | Design evidence and threat model; video-specific claims remain subject to transcript-level verification |
| `https://github.com/karpathy/autoresearch` at `228791fb499afffb54b46200aca536f79142f117` | `SRC-021` | Verified, MIT | Primary engineering evidence for a bounded autonomous propose/measure/keep-or-discard experiment loop |

The source URL is fingerprinted into the founding vision contract. Partial ingestion remains a blocking evidence obligation; this document does not claim timestamp-complete coverage of the video.

## Question presented

How should Hive Mind OS incorporate recursive self-improvement without allowing agents to rewrite their mission, expand authority, reward-hack metrics, mutate a live champion, consume unbounded resources, or promote noisy regressions?

## Advocate case

A bounded form of recursive improvement is directly useful to Hive Mind OS:

1. Start from a versioned champion.
2. Form a falsifiable improvement hypothesis.
3. Create an isolated challenger rather than editing the champion in place.
4. Run repeated experiments under a pinned evaluation contract and fixed resource envelope.
5. Compare the challenger against the champion using a primary metric plus hard guardrails.
6. Keep only an independently reproduced improvement; otherwise retest, discard, quarantine, or stop.
7. Record all artifacts, failed attempts, causes, costs, and lessons.
8. Use the retained champion as the parent for the next eligible experiment.

This turns trial and error into a compounding institutional learning process rather than a one-off coding session.

## Cross-examination

Recursive loops create failure modes that ordinary agent workflows do not adequately address:

- **Goodhart and metric gaming:** a candidate can improve the measured score while defeating the real objective.
- **Evaluation leakage:** access to protected holdouts can create false evidence of progress.
- **Self-approval:** the same actor can write, test, and grade a candidate to manufacture promotion.
- **Noise promotion:** tiny random changes can be mislabeled as improvement.
- **Guardrail sacrifice:** speed or benchmark score can improve by degrading correctness, trust, security, maintainability, latency, or cost.
- **Live mutation:** editing the champion in place destroys reproducibility and rollback.
- **Diminishing returns:** an unbounded loop can consume increasing resources for decreasing value.
- **Opacity:** generated code may become difficult to understand or audit even when a headline metric improves.
- **Strong-RSI escalation:** changing model weights, mission, policy, identity, replication behavior, or resource authority is fundamentally different from optimizing bounded external artifacts.

## Judgment

Hive Mind OS **adapts weak recursive improvement** and **rejects unrestricted strong recursive self-improvement**.

### Adopted mechanism

The implementation in `src/hive_mind_os/recursive_improvement.py` provides:

- immutable `RecursiveImprovementContract` fingerprints;
- versioned `ExperimentCandidate` lineage and mandatory rollback references;
- repeated baseline and candidate measurements;
- direction-aware primary and guardrail metrics;
- measured noise floors and minimum effect thresholds;
- independent evaluator identity checks;
- protected-holdout, policy, artifact, and metric-gaming quarantine gates;
- deterministic `KEEP`, `RETEST`, `DISCARD`, `QUARANTINE`, and `STOP` verdicts;
- patience and maximum-experiment stopping conditions;
- a controller that promotes only descendants of the active champion while retaining every decision.

### Non-delegable boundaries

No recursive-improvement workflow may:

- mutate the active champion in place;
- alter the mission charter or policy engine;
- evaluate its own candidate as independent evidence;
- access protected holdouts before the prediction is sealed;
- optimize a single metric without hard guardrails;
- promote a result below the measured noise floor;
- conceal failed attempts or side effects;
- modify its own model weights under routine-work authority;
- replicate, acquire credentials, purchase resources, or expand infrastructure without an external grant;
- continue after configured patience, budget, or stop conditions are reached.

## Court dispositions

| Claim | Disposition | Result |
|---|---|---|
| `CLM-067` bounded weak RSI and challenger-only mutation | Adapt / implemented | External artifacts may improve; live champion, mission, policy, and weights remain immutable |
| `CLM-068` propose-to-verdict experiment state machine | Adapt / implemented | Every attempt has artifacts, lineage, rollback, and a durable verdict |
| `CLM-069` repeated noise-aware measurements | Adapt / implemented | Sub-noise lifts are retested or stopped, never promoted |
| `CLM-070` reward-hacking and leakage disqualification | Adapt / implemented | Gaming, leakage, self-evaluation, missing artifacts, and policy violations quarantine the candidate |
| `CLM-071` multi-objective guardrails | Adapt / implemented | Primary gains cannot outweigh hard trust, quality, security, latency, cost, or resource regressions |
| `CLM-072` diminishing-return stopping rules | Adapt / implemented | Patience and experiment limits terminate low-value recursive loops |
| `CLM-073` strong RSI boundary | Adapt / constitutional | Self-weight, mission, policy, concealment, replication, and authority expansion remain prohibited |

## Acceptance evidence

`tests/test_recursive_improvement.py` verifies:

- significant repeated improvements are kept;
- metric gaming and holdout access quarantine candidates;
- actors cannot independently evaluate their own work;
- hard guardrail regressions discard candidates;
- noisy marginal lifts are retested rather than promoted;
- diminishing returns trigger deterministic stopping;
- contract mutation and missing artifacts fail closed;
- stale candidates cannot replace the current champion;
- rejected and quarantined experiment history remains retained.

## Outcome metrics

The Optimizer and Curator should report at least:

- verified improvement rate;
- false-promotion and rollback rate;
- effect size over measured noise;
- guardrail regression rate;
- metric-gaming and holdout-leakage escape rate;
- cost and latency per verified improvement;
- experiments per retained improvement;
- marginal value per compute unit;
- human intervention rate;
- percentage of experiments with complete artifacts and reproducible verdicts.

## Appeal path

Complete transcript ingestion, timestamped exhibits, verified experiment artifacts, or stronger primary research may reopen individual claims. New evidence may tighten or expand bounded weak-RSI capabilities, but it cannot silently remove the constitutional restrictions above.
