# Phase 2 dissent and limitations

1. A unified store concentrates sensitive metadata and can bottleneck concurrent
   writers. Phase 2 mitigates but does not eliminate that risk.
2. SQLite transactional outbox proves local durability only. It does not provide
   exactly-once external delivery or atomicity with Generation Zero databases.
3. Provider-shaped fixtures prove parser behavior, not live provider billing,
   pricing, model identity, cache, or reasoning conformance.
4. A digest of low-entropy content can leak information. Foundation records therefore
   default private and reject bodies; a later keyed-reference/crypto-erasure design
   may still be required.
5. Append-only evidence and legal deletion can conflict. Tombstone/retention records
   do not claim physical deletion.
6. Semantic retrieval is not implemented as a model or vector index in Phase 2.
   Callers may supply offline candidates, but only an evidence-bearing classification
   may relate them.
7. The opt-in provider wrapper measures physical provider attempts but does not
   reinterpret Generation Zero invalid-output semantics or activate a new backend.
8. OpenTelemetry vocabulary is evolving and replaceable. The local envelope is not
   accounting truth and outbound export is disabled.
9. No superiority, production readiness, live-provider support, Obsidian behavior,
   or autonomous learning/control claim is made.
10. UUID physical-attempt identity makes accidental collision negligible but is not a
    distributed identity authority. Cross-host coordination remains outside Phase 2.
11. Safe-public enforcement proves that an explicit independent release bit was
    carried into the write decision; it does not implement a publication workflow.
12. The schema-object digest detects malformed or drifted local databases. It is an
    integrity/admission receipt, not cryptographic protection against an attacker who
    can rewrite both schema and metadata.
