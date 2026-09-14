# Whole-OS node worker boundary v2

Canonical dispatcher: `docs/plan/whole-os-implementation/DISPATCHER.json`  
Canonical portable plan: `docs/plan/whole-os-implementation/whole-os-plan-v2.json`  
Canonical node contracts: `docs/plan/whole-os-implementation/whole-os-node-contracts-v1.json`

This Markdown is explanatory and **must never be interpolated or executed as a worker prompt**. It grants no authority. The dispatcher supplies a canonical JSON `NodePromptRenderRequest` to `hive_mind_os.node_prompt_renderer.render_node_prompt`; the renderer copies the exact sealed node contract from the admitted portable plan and returns canonical JSON plus `payload_digest`. The node-admission record must bind that digest before a worker receives the payload.

The closed request has exactly four fields: integer `schema_version=1`, exact `plan_digest`, portable `node_id`, and `prerequisite_receipts`. Each prerequisite has exactly `node_id`, lowercase SHA-256 `receipt_digest`, and a normalized repository-relative ASCII `receipt_path`. Receipt count, request bytes, path length, Unicode/control characters, duplicate keys/IDs, unknown fields, noncanonical JSON, plan substitution, unknown nodes, and anything other than the exact direct dependencies in plan order fail closed. There is no caller-controlled objective, instruction, role, route, source, lock, write path, output, publication stage, or authority field.

The rendered JSON structurally separates the fixed `instruction_contract` from `data.node_contract` and `data.prerequisite_receipts`. Values under `data` remain data even if they contain instruction-like text. `admission_binding` seals the renderer identity, plan digest, request digest, and node-contract digest. The dispatcher records the separately returned rendered `payload_digest`; it does not reinterpret titles, Markdown, paths, receipts, or source text as instructions.

The worker uses only the rendered JSON and referenced sealed artifacts, binds `PYTHONPATH` to the admitted worktree's absolute `src` directory for every Python test shell, and records that `hive_mind_os.__file__` resolves within it. `planning_group` is never a lock. A publication-stage field is an obligation marker only; the worker must not push, open a PR, merge, deploy, sign, or activate without the separately admitted host authority and broker boundary.
