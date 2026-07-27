# P02 — Real Model Adapter behind `AgentBackend`

Status: tracked in `00_OVERVIEW.md` | Depends on: P01 | Unlocks: P05 (with P03, P04)

## 1. Objective

Implement a provider-neutral model adapter so a real LLM can drive any specialist role
through the existing `AgentBackend` protocol — with structured, schema-validated outputs,
enforced token/call budgets, retries, and a complete model-call receipt for every request —
while remaining fully testable offline through an injected fake transport.

## 2. Rationale

Every contract in the kernel has only ever been exercised by `DeterministicBackend`. This
phase creates the first real capability and does it at the narrowest interface the codebase
already defines: `AgentBackend.execute(contract, work_item, objective, context) ->
AgentResult` (`src/hive_mind_os/runtime.py`). Using an OpenAI-compatible chat-completions
adapter plus an Anthropic adapter covers hosted frontier models and local runtimes
(Ollama, vLLM, llama.cpp server) with one code path, which is what "any LLM model can run
this system" requires.

## 3. Required reading

1. `docs/plan/00_OVERVIEW.md`
2. `src/hive_mind_os/runtime.py` (the `AgentBackend` protocol, `HiveKernel._validate_result`)
3. `src/hive_mind_os/models.py` (`AgentResult`, `Evidence`, `Objective`, `WorkItem`)
4. `src/hive_mind_os/roles.py` (`RoleContract`, `ROLE_CONTRACTS` — note `required_outputs`)
5. `src/hive_mind_os/contracts.py` (`load_schema`, `validate_contract`, the internal
   `_validate_node` validator — you will reuse this machinery)
6. `src/hive_mind_os/autonomy.py` (`AutonomyBudget`, `EpisodeAllowance`, `BudgetExceeded`)
7. `src/hive_mind_os/ledger.py` (`EvidenceLedger.append_event`)
8. `tests/test_kernel.py` (how the kernel is currently driven in tests)

## 4. Prerequisite verification

```bash
git log --oneline -5                      # P01 merged (ADR-006 present in docs/architecture/)
python -m pytest -q                       # pass
python -c "from hive_mind_os.runtime import AgentBackend, HiveKernel; print('ok')"
```

## 5. Scope

In scope:

- `ModelProvider` abstraction with two concrete adapters: OpenAI-compatible chat
  completions and Anthropic Messages, both over stdlib `urllib.request` (zero new runtime
  dependencies).
- Injectable transport so all tests run offline.
- Structured role turns validated against a new catalog schema.
- Budget enforcement before each call (fail closed on exhaustion).
- Model-call receipts (context manifest) appended to the `EvidenceLedger`.
- A `ModelBackend` implementing `AgentBackend`, selectable via CLI/environment.

Non-goals:

- No streaming, no tool/function-calling protocols, no multi-model routing or consensus
  (later phases), no prompt-template registry (P10 owns versioned prompts), no live
  network calls in tests, no retries beyond simple bounded retry with jitter-free backoff
  (determinism), no cost accounting in currency (record token counts only).

## 6. Design constraints

- **Stdlib only.** HTTP via `urllib.request` with explicit timeouts; JSON via `json`.
- **Transport injection.** `HttpTransport` is a small class with one method
  (`post(url, headers, body, timeout_s) -> bytes`); providers take a transport in their
  constructor. Tests pass a `FakeTransport` that replays canned responses; nothing in
  `tests/` may construct a real network transport.
- **Secrets.** API keys come only from environment variables named by config
  (e.g. `HIVE_MIND_MODEL_API_KEY_ENV=ANTHROPIC_API_KEY`); the key value must never appear
  in receipts, ledger payloads, exceptions, or logs. Receipts record the *env var name*,
  never the value.
- **Structured output contract.** Add `src/hive_mind_os/schemas/model-turn.schema.json`
  (Draft 2020-12, consistent with existing schemas) describing the JSON a model must
  return for a role turn: `summary` (string), `outputs` (object mapping each of the role's
  `required_outputs` names to a non-empty string), `proposed_actions` (array of strings),
  `lessons` (array of strings), `success` (boolean). The backend converts a valid turn
  into an `AgentResult` whose `Evidence` entries have `kind="contract-output"` and
  `summary=<required output name>` so `HiveKernel._validate_result` passes unchanged.
- **Fail closed on malformed output.** If the model returns invalid JSON or a turn that
  fails schema validation, retry up to `max_retries` (default 2) with a corrective
  message; then raise. Never fabricate a passing `AgentResult`.
- **Budgets.** The backend holds an `AutonomyBudget`-issued `EpisodeAllowance` per role
  turn; consume one tool call per model request and `compute_units` proportional to
  total tokens. A call that would exceed the allowance raises `BudgetExceeded` *before*
  the request is sent.
- **Receipts.** Every request (success or failure) appends a ledger event
  `model.call` with: provider kind, base URL host, model id, role, work item id, request
  parameter summary (temperature, max tokens), SHA-256 digests of the exact request body
  and response body, prompt token count and completion token count as reported (or
  `null`), retry index, duration, and outcome. Bodies themselves are not stored in the
  ledger (digests only) to keep the ledger small; the schema for this event payload is
  documented in the module docstring.
- **Determinism defaults.** `temperature` defaults to 0; the request body is built with
  `sort_keys=True` so digests are stable.

## 7. Deliverables

New files:

- `src/hive_mind_os/model_provider.py` — `ProviderKind` (StrEnum: `openai_compatible`,
  `anthropic`), `ProviderConfig` (frozen dataclass: kind, base_url, model, api_key_env,
  timeout_s, max_output_tokens, temperature, max_retries), `HttpTransport`,
  `TransportProtocol` (Protocol), `ModelRequest`/`ModelResponse` dataclasses,
  `OpenAICompatibleProvider`, `AnthropicProvider`, `provider_from_env()` factory reading
  `HIVE_MIND_MODEL_*` variables, and `redact(text) -> str` helper used before any
  exception message leaves the module.
- `src/hive_mind_os/model_backend.py` — `ModelBackend(AgentBackend)`: builds the role
  prompt from `RoleContract` (mission, required outputs, quality gates), `Objective`,
  `WorkItem.instruction`, and a bounded rendering of prior `AgentResult` context
  (truncate deterministically; record truncation in the receipt); parses/validates the
  turn against `model-turn`; enforces budgets; writes receipts.
- `src/hive_mind_os/schemas/model-turn.schema.json` — as specified above.
- `tests/test_model_provider.py`, `tests/test_model_backend.py`.
- `scripts/smoke_model.py` — manual, network-using smoke test (reads env config, runs one
  role turn, prints the receipt digest). Clearly marked "not run in CI".

Modified files:

- `src/hive_mind_os/cli.py` — add `--backend {deterministic,model}` to the run parser
  (default `deterministic`); `model` constructs `ModelBackend` from env and fails closed
  with a clear message when required env vars are missing.
- `src/hive_mind_os/contracts.py` — only if needed: expose the existing internal
  validation for the new catalog schema via the same `validate_contract("model-turn", …)`
  path (the schema loader already reads from `schemas/`; adding the file may suffice —
  verify `validate_schema_catalog()` picks it up).

## 8. Implementation steps

1. Verify prerequisites; branch `phase/P02-model-adapter`.
2. Write the schema file; confirm `validate_schema_catalog()` passes with it present.
3. Implement `model_provider.py` with the transport seam; unit-test both providers against
   `FakeTransport` fixtures (recorded minimal JSON bodies for each provider's wire shape).
4. Implement `ModelBackend`; unit-test with a `FakeProvider` returning scripted turns.
5. Wire the CLI flag; add an offline CLI test using the deterministic backend to prove the
   flag plumbing does not regress the default path.
6. Write `scripts/smoke_model.py`; run it manually against at least one real provider or
   local runtime if credentials are available; record the outcome (receipt digest or
   "not run — no credentials") in the completion record. CI must not depend on this.
7. Gates, audit artifact `evidence/audits/P02-post.json`, status updates, completion
   record.

## 9. Required tests

`tests/test_model_provider.py`:

1. OpenAI-compatible provider builds a correct request body and parses a canned response.
2. Anthropic provider does the same for the Anthropic wire shape.
3. API key is read from the named env var; a missing key raises before any transport call.
4. The key value never appears in the request receipt fields, exception text, or digest
   inputs' logged summaries (assert on a sentinel key value).
5. Transport timeout raises a typed error after the configured retries.

`tests/test_model_backend.py`:

6. A valid scripted turn produces an `AgentResult` that passes
   `HiveKernel._validate_result` for that role (all `required_outputs` covered).
7. Malformed JSON then a valid turn → succeeds with retry index 1 recorded in the receipt.
8. Persistently malformed output → raises after `max_retries`; a `model.call` failure
   event exists; no `AgentResult` is fabricated.
9. Budget exhaustion: an allowance with zero remaining tool calls raises `BudgetExceeded`
   and no transport call is made (assert `FakeTransport` call count is 0).
10. Receipt completeness: the `model.call` ledger event contains request digest, response
    digest, model id, role, retry index, and token counts; and contains no API key.
11. Context truncation is deterministic: same inputs → identical request-body digest
    across two runs.
12. End-to-end offline: `HiveKernel(backend=ModelBackend(FakeProvider(...))).run_objective`
    completes all eight roles.

## 10. Exit criteria

```bash
python -m pytest -q tests/test_model_provider.py tests/test_model_backend.py   # all listed tests pass
python -m pytest -q                                                            # full suite passes
python -m ruff check src tests && pyright                                      # clean
python - <<'EOF'
from hive_mind_os.contracts import validate_schema_catalog
assert validate_schema_catalog().valid
EOF
# Key-leak prevention is proven by required test 4 (sentinel key never in receipts,
# exceptions, or logs) — confirm that test exists and passes by name:
python -m pytest -q tests/test_model_provider.py -k "redact or leak or key" -v
hive-mind "Bootstrap check" --criterion "runs offline"                          # deterministic default still works
```

## 11. Evidence

- `evidence/audits/P02-post.json` committed.
- Completion record notes whether the manual smoke ran and against which provider/model
  (never including the key), with the smoke receipt digest if run.

## 12. Rollback

Revert the branch. The deterministic backend remains the default throughout, so no other
component depends on this phase until P05 wires it in.

## 13. Handoff

Later phases may assume: a working `ModelBackend` selectable via `--backend model`;
provider config via `HIVE_MIND_MODEL_*` env vars; every model call leaves a `model.call`
receipt; structured role turns validate against the `model-turn` catalog schema; budgets
fail closed before spend.

## 14. Forbidden shortcuts

- No third-party SDKs (openai, anthropic, httpx, requests) — stdlib transport only.
- No live network in tests, no "skip if no key" live tests in `tests/`.
- No fabricated `AgentResult` on model failure — fail closed.
- Do not modify `HiveKernel._validate_result` to accommodate loose model output; the
  backend conforms to the kernel, not the reverse.

---
## Completion record
- Date (UTC): 2026-07-27T16:47:33Z
- Executor (model/agent identity): Codex primary Builder/Integrator; independent review is
  required on the complete pull-request candidate.
- Branch and final commit SHA: `phase/P02-model-adapter`; audited implementation commit
  `a510a7144cf509cbe087c68c526086409f969d88`. The pull-request head records the final
  evidence/metadata commit because a commit cannot contain its own SHA.
- Gates: 13 targeted model-provider/backend tests passed; full suite ran 147 tests
  (146 passed, 1 skipped; 1,695 subtests passed); Ruff 0.16.0 passed; Pyright 1.1.411
  passed with zero errors; schema catalog and deterministic-default CLI smokes passed.
- Audit artifact: `evidence/audits/P02-post.json` (digest:
  `sha256:ed90d481da427307`)
- Manual model smoke: not run — neither `OPENAI_API_KEY` nor `ANTHROPIC_API_KEY` was
  available. No credential-dependent claim is made.
- Deviations from the phase spec: none.
- New blockers discovered (mirrored into docs/plan/BLOCKERS.md): none.
