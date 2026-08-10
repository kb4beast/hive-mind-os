# Model Routing

Use the lowest route that can satisfy the node contract safely. The dispatcher must verify current
model availability before every wave because model catalogs change.

- **T0:** deterministic/mechanical. OpenAI GPT-5.6 Luna low; Anthropic current Haiku discovered at runtime.
- **T1:** narrow bounded implementation. GPT-5.6 Luna medium or Claude Sonnet 5 low.
- **T2:** moderate multi-file/reconciliation. GPT-5.6 Terra medium or Claude Sonnet 5 medium.
- **T3:** cross-cutting/concurrency/security. GPT-5.6 Sol high or Claude Opus 4.8 high.
- **T4:** kernel/authority/anti-cheating/promotion. GPT-5.6 Sol max or Claude Fable 5 highest available.

Escalate model tier only after preserving the lower-tier failure and identifying the specific
capability gap. A higher model does not grant broader file, effect, credential, or acceptance
authority.

## Execution surface

Model tier and execution surface are separate. **ChatGPT Classic is always attempted first**, even for code work. Use its available GitHub/connectors, files, web, and deterministic tools to complete as much of the node as possible. Codex is permitted only for the smallest remaining action that requires a capability Classic actually lacks (for example local shell/test/build/benchmark execution). Keep the Codex prompt short, return its evidence to Classic, and resume the node in Classic.
