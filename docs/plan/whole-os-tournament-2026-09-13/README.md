# Whole-system Hive Mind OS tournament and implementation handoff

**Owner request:** 2026-09-13, America/Chicago. **Artifact status:** documentation-only design tournament and future implementation specification. **Inspected baseline:** `d980a9cfe39f68b3de86ea0530234b3ab4e91390`, tree `47f873cf5924b97cfafafe1b9dfb0a450acb2e92`. No implementation, runtime activation, provider benchmark, PR publication, merge, or deployment is performed by this package.

The proposed direction is an autonomous repository service that discovers valuable work, builds and repairs it in isolated workspaces, independently qualifies candidates, opens PRs, observes outcomes, and improves through separately evaluated challengers. Hive Mind OS is one supported subject; external repositories use the same service through explicit repository and domain adapters. The DAG directs work from outside the application. Delivered applications do not acquire a dependency on Hive Mind OS's execution workspace.

The design favors flexible implementation inside meaningful work packages. It does not require a new debate, full repository scan, full test suite, or all eight model calls for every edit. It preserves exact-candidate qualification, private-data boundaries, durable recovery, and separately authorized remote effects.

Read these files in this order:

1. [RUNBOOK.md](RUNBOOK.md): decisions, data contracts, worker rules, routing, execution waves, and definition of done.
2. [TOURNAMENT.md](TOURNAMENT.md): field, component alternatives, analytical triple-elimination results, hybrids, dissent, and unperformed benchmark obligations.
3. [NODES-FOUNDATION.md](NODES-FOUNDATION.md): N00–N07, baseline, contracts, efficiency and routing.
4. [NODES-EXECUTION.md](NODES-EXECUTION.md): N08–N17, autonomous runtime, discovery, implementation, verification, PRs and self-upgrades.
5. [NODES-LEARNING.md](NODES-LEARNING.md): N18–N27, isolation, lessons, endpoint training and Roblox qualification.
6. [NODES-QUALIFICATION.md](NODES-QUALIFICATION.md): N28–N33, integrated tests, measured tournament and staged operation.
7. [SOURCES.md](SOURCES.md), [REVIEW.md](REVIEW.md), [requirements.json](requirements.json), and [dag-index.json](dag-index.json): evidence, review, requirement coverage, and dependency index.

The package includes 34 node contracts and 283 numbered implementation steps. [validation.json](validation.json) records the documentation/data checks; [MANIFEST.json](MANIFEST.json) records content hashes. These validate the handoff's structure, not the future software.

**For a smaller implementation model:** start with the universal worker contract in RUNBOOK and your single assigned node. Load direct prerequisite receipts and only the source sections named there. The index is inert planning data, **not** a `PortablePlanBundle`, authority grant, or runnable `.autopilot/plan.json`. N00/N01 reconcile and compile a successor before execution. Existing plans and signed histories are never overwritten with this package.

**Important interpretation:** external application code PRs belong to the target application's repository. Its contribution back to Hive Mind OS is a separate, sanitized **lessons-only draft**. That draft cannot silently become active memory or a self-upgrade. If export is unavailable, retain the draft privately and keep the export obligation visible while authorized application work continues.

**What remains unproven:** production autonomy, speed gains, safe use of arbitrary hostile repositories, training improvements, and production Roblox games. This package specifies the experiments and receipts needed to establish those claims. Public first/final examples alone cannot establish them.
