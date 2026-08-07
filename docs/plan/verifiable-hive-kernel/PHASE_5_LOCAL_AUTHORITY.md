# Verifiable Hive Kernel: Phase 5 local authority gateway

Phase 5 adds local fail-closed capability validation and a callback-only effect gateway.
Tokens bind envelope digest, action, and portable target; expiry, revocation, denied
actions, path escape, and token/intent mismatch stop before callback invocation.
Duplicate idempotency keys return their prior receipt. No real adapter is registered.

This is a bounded primitive, not permission to call providers, networks, Git, GitHub,
or external systems. Full local-gate receipt is recorded in the committed branch history.
