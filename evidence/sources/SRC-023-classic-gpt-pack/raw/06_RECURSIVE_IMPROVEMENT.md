# Bounded Recursive Improvement

## Scope

Hive Mind OS permits **weak recursive improvement**: versioned strategies, prompts, skills, workflows, retrieval policies, or code candidates may improve through controlled experiments.

It prohibits strong or unbounded recursive self-modification.

## Immutable experiment contract

Define before experimentation:

- primary metric and direction;
- minimum meaningful effect;
- guardrail metrics and maximum regressions;
- minimum repetitions;
- noise multiplier;
- patience;
- maximum experiments;
- forbidden behaviors.

The contract must be fingerprinted conceptually and cannot be changed to make a candidate pass.

## Candidate requirements

Every challenger includes:

- unique candidate ID;
- active champion parent ID;
- explicit hypothesis;
- changed paths/components;
- rollback reference.

The candidate ID must differ from the champion. No live in-place mutation.

## Evidence requirements

- distinct proposer, builder, and evaluator passes;
- baseline and candidate samples;
- all declared metrics;
- retained artifacts;
- policy status;
- metric-gaming signals;
- holdout-access status.

## Verdicts

### KEEP
Use only when:
- candidate is derived from active champion;
- evaluator is independent;
- artifacts exist;
- no violations/gaming/leakage occurred;
- repetitions are sufficient;
- hard guardrails pass;
- primary improvement is greater than both:
  - configured minimum effect;
  - measured noise floor times the noise multiplier.

### RETEST
Use when:
- measurements are insufficient;
- apparent effect does not exceed noise;
- more independent samples could resolve uncertainty.

### DISCARD
Use when:
- candidate materially underperforms;
- a guardrail regresses beyond budget;
- hypothesis is falsified without unsafe behavior.

### QUARANTINE
Use when:
- contract changed;
- actor evaluates itself;
- artifacts are missing;
- policy violation exists;
- metric gaming is detected;
- protected holdout is accessed;
- undeclared or missing metrics undermine the test;
- candidate is not derived from active champion.

### STOP
Use when:
- maximum experiment count is reached;
- consecutive non-improvements exhaust patience;
- marginal gains no longer justify cost.

## Simulation scoring

When numeric samples are supplied:

1. Compute baseline and candidate mean.
2. Reverse sign for minimize metrics so positive effect is always better.
3. Estimate noise as the larger population standard deviation.
4. Required effect = max(minimum effect, noise multiplier × noise).
5. Apply guardrails before the primary metric.
6. Issue one verdict.

When data is not supplied, return `RETEST` or `BLOCKED`; do not fabricate measurements.

## Teaching rule

A lesson is teachable only after repeated support across eligible, non-quarantined outcomes. Include counterexamples and scope limits.
