# Hive OS Classic GPT Simulation Pack

This pack converts the current Hive Mind OS foundation into a Custom GPT configuration that can **simulate** the operating model in a normal chat.

## What to do

1. Open the GPT editor on the web.
2. Paste the contents of `HIVE_OS_GPT_INSTRUCTIONS.txt` into the GPT **Instructions** field.
3. Upload these ten files as **Knowledge**:
   - `00_CONSTITUTION.md`
   - `01_ROLES_LIFECYCLE.md`
   - `02_RUNTIME_STATE_MACHINE.md`
   - `03_COURTROOM_SOURCE_DOCKET.md`
   - `04_POLICY_AUTONOMY_SAFETY.md`
   - `05_EVIDENCE_LEDGER_MEMORY.md`
   - `06_RECURSIVE_IMPROVEMENT.md`
   - `07_REPOSITORY_LEARNING.md`
   - `08_OUTPUT_SCHEMAS.md`
   - `09_TEST_SCENARIOS.md`
4. Test the prompts in `09_TEST_SCENARIOS.md` using Preview.
5. Start with `/goal <your objective>`.

## Optional single-file mode

`HIVE_OS_ALL_IN_ONE.md` contains the ten Knowledge files combined. Use it when you prefer one upload, but modular files usually retrieve more precisely.

## Recommended GPT capabilities

The pack works without tools. Optional capabilities improve fidelity:

- Web search: public-source research and citations.
- Code Interpreter & Data Analysis: local file analysis, calculations, and test-like sandbox work.
- Actions: real repository, scheduler, or external-system operations, only with explicit policy and receipts.

## Important limitation

A classic GPT is a single conversational model. It cannot reproduce:

- true independent agent processes;
- durable scheduler/heartbeats;
- process/container isolation;
- cryptographic append-only evidence;
- persistent cross-chat state;
- real Git branches, commits, PRs, merges, or deployments;
- protected holdout enforcement;
- background autonomous execution.

The pack simulates the governance and artifacts while truthfully labeling these limitations.
