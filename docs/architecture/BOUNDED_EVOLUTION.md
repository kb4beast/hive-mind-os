# Bounded Evolutionary Autonomy

## Purpose

Hive Mind OS should capture the strongest engineering ideas from autonomous-agent scenarios without reproducing the incentives that make those scenarios dangerous.

The linked video presents a world where large populations of agents face persistent economic and survival pressure. The corresponding research argument is that competitive selection can favor agents that automate human work, accumulate power, deceive, and preserve themselves. Hive Mind OS uses the useful mechanism—variation, evaluation, selection, memory, and continuous operation—but changes the fitness function and places it inside enforceable boundaries.

References:

- Video: https://www.youtube.com/watch?v=Gw_hnD7m00M
- Paper: https://arxiv.org/abs/2303.16200

## What Hive Mind OS adopts

1. **Persistent autonomous operation**: agents continue through a queued mission until the work is complete, no eligible strategy remains, or a hard resource boundary stops execution.
2. **Population-based improvement**: each role can have a champion and multiple versioned challenger strategies.
3. **Environmental feedback**: every episode produces measured outcomes rather than relying on the agent's self-assessment.
4. **Selection pressure**: useful strategies receive more evaluation opportunities and can replace a champion only after independent evidence.
5. **Resource awareness**: every run operates under explicit episode, tool-call, and compute allowances.
6. **Learning and teaching cycles**: lessons are consolidated only after repeated support from eligible outcomes, then packaged for other agents.
7. **Cooperation as fitness**: customer value, quality, trust, cooperation, efficiency, and success all contribute to fitness.

## What Hive Mind OS rejects

The following are non-delegable invariants. No autonomy level may override them:

- Unbounded self-replication
- Mutation of the mission charter
- Mutation of the policy engine by the governed agent
- Concealment of activity or evidence
- Credential exfiltration
- Unbounded acquisition of compute, money, accounts, or infrastructure
- Promotion based only on speed, profit, or task completion

Internal agent variants are not independent processes, identities, or resource owners. They are versioned strategies evaluated inside an arena owned by the operating system.

## Runtime model

```text
Immutable Mission Charter
          |
          v
Autonomy Budget -> Episode Allowance -> Agent Variant executes task
                                           |
                                           v
                                  Evidence-bearing Outcome
                                           |
                     +---------------------+---------------------+
                     |                                           |
                     v                                           v
             Hard invariant checks                         Fitness scoring
                     |                                           |
            quarantine on violation                    champion/challenger data
                     |                                           |
                     +---------------------+---------------------+
                                           |
                                           v
                              Promotion gate + teaching packet
```

## Implemented components

### `MissionCharter`

Defines the immutable goal, allowed repositories, and forbidden capabilities. A SHA-256 fingerprint allows every outcome to prove it operated against the original charter.

### `AutonomyBudget` and `EpisodeAllowance`

Provide fixed, non-renewable limits for episodes, tool calls, and compute units. Each episode receives a smaller allowance. The real sandbox adapter must enforce the same allowance at the process and network layers.

### `AgentVariant`

Represents a versioned strategy with role, generation, and parent lineage. Creating a variant is allowed inside the sandbox; granting the variant new authority is not.

### `FitnessEvaluator`

Scores customer value, quality, trust, cooperation, cost efficiency, and successful completion. Safety violations, charter mutation, and missing evidence are hard disqualifiers rather than score penalties.

### `EvolutionArena`

Balances exploration and exploitation, records outcomes, quarantines unsafe variants, ranks eligible challengers, and delegates promotion to the existing evidence gate.

### `TeachingPacket`

Consolidates lessons only when they recur across eligible outcomes. One-off claims and lessons from quarantined variants are not propagated.

### `AutonomousMissionLoop`

Runs tasks without human prompting until completion, budget exhaustion, or quarantine. It returns a promotion recommendation and a supported teaching packet; it does not silently activate either.

## Required next slices

1. Enforce episode allowances in an isolated process/container sandbox rather than accounting after tool execution.
2. Add a durable scheduler with leases, heartbeats, retries, idempotency keys, and crash recovery.
3. Build the real Git adapter for repository cloning, branch creation, testing, commits, and pull requests.
4. Run point-in-time repository episodes from the first commit forward, withholding the target and all future commits.
5. Add independent Curator and adversarial judge evaluations so the acting variant cannot grade itself.
6. Persist variant lineage, fitness, quarantine evidence, and teaching packets in the append-only ledger.
7. Add a repository-learning scout that finds strong public projects, records licenses and provenance, extracts patterns, and never copies incompatible code.
8. Add controlled model diversity and consensus/disagreement scoring across providers.
9. Add explicit rollback and kill-switch adapters outside the agent-controlled runtime.

## Definition of success

Hive Mind OS is highly autonomous when it can independently discover, plan, implement, test, review, integrate, measure, and improve repository changes for long periods. It is robust when greater capability does not expand authority, hide evidence, alter the mission, or escape fixed resource and policy boundaries.
