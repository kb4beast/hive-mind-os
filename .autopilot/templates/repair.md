## Mandatory execution-surface policy

Read `.autopilot/workflow-policy.json`. **This durable primary task owns this node** through its stopping condition. Use the approved host's available reasoning, repository/GitHub tools, files, shell, and deterministic controller directly. Host choice never expands authority.

The parent creates the complete visible task cohort before its first wait. Task creation
is not claim or write authority: the title and prompt state either `EXECUTION_AUTHORIZED`,
`RECOVERY_AUTHORIZED`, or `PREPARATION_ONLY`. A preparation-only task may inspect,
diagnose, and prepare a handoff but must not mutate repository or remote state.

Nested agents are bounded sidecars for research, independent review, or non-blocking validation; they do not replace this primary task. If a required capability is unavailable, return an exact typed capability blocker to the parent. The parent must repair or select an approved capable host and resume this same node rather than asking the user to perform repairable work.

If genuine human action remains, never assume prior knowledge: give exact click-by-click UI steps or copy-paste commands, what should appear, what to send back, and safety/rollback guidance.

Every final response must contain `WHAT I DID`, `NEXT STEPS`, and `BLOCKS`; use `None.` for BLOCKS when clear.

Parallel tasks may run focused checks only. Before any repository-wide validation,
acquire the singleton lease with `validation-lease-acquire`; if another owner holds it,
stop the duplicate run, preserve it as non-verdict evidence, notify the parent, and do
not retry. Release the lease after the one authoritative run.

Read `.autopilot/README.md`, the node contract, prior receipt/failure evidence, the open
PR, and failing CI logs. Repair only the accepted node scope. Do not restart the node
from memory, broaden authority, weaken tests, erase adverse evidence, or switch models
without recording the escalation reason. Re-run exact candidate verification and append
a new receipt. Stop at a green draft PR; do not merge.
