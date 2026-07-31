# Phase 5A installed-wheel receipt

- Verification boundary: local isolated-wheel import and deterministic contract execution
- Distribution: `hive-mind-os==0.6.0`
- Wheel: `hive_mind_os-0.6.0-py3-none-any.whl`
- Wheel SHA-256: `7d8f17406c5f54dee5c02d3c1e22590ab655da89629dfe11849edc56c930ebf3`
- Verification JSON SHA-256: `73c1f76efb9683e6673f11cca376881f283374cfec0d7be0cd34dc765bca91ee`
- Governed JSON resources retained: 133
- Governed components retained: 22
- Trust posture retained: quarantined

## Verified Phase 5A subject

- Successor digest: `sha256:e2e6f8ee8975db17a002fafc7d78aa5e2f696540e2ce4404d4548785643528fc`
- Example request digest: `sha256:b216e25d35195a5c648609fa34e635d52a607c7e4e088d9e01e2917ef1aa29b0`
- Example plan digest: `sha256:482c1f8e9a736ae92858ba01b2c64a2e92a1e2a29d4a2ad5d6086d2401d3b5ea`
- Strict schemas: 10
- Typed outputs: 7
- Work items: 7
- Dependency edges: 21
- Handoff required references in example: 4
- Maximum handoff references: 128
- Stop decision: `defer`
- Handoff role: `curator`
- Independence status: `procedural-only`
- Verification receipt paths: installation-root-relative and reproducible
- Evidence status: `claimed-unverified`
- Effective capabilities: 0
- Tools: 0
- Authority: none
- Activation: inert
- Authenticated distinct actors: false
- Completion authorized: false
- Activation authorized: false

## Limits

The local environment supplied `setuptools 82.0.1`, so this receipt does not replace the hosted
build gate for the repository-pinned `setuptools==83.0.0`. Exact-head hosted CI must rebuild,
install, verify, generate the SPDX SBOM, and attest the final subjects before technical
completion. This receipt does not authorize merge, runtime selection, activation, production
readiness, release readiness, value, learning, promotion, or superiority.
