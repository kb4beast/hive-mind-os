# Fixture prerequisite causality reseal v2

This six-node, evidence-only Appeals-Judge reseal corrects the source identity
defect in the superseded FPC appeal.  Every claim is evaluated only against
commit `b789b68e7d6a741e0b85a3ac33cbce846e1e32c9` and its real tree
`b909b7b7e374bff22912059387ef0fe639498af6`.  The former tuples
`20e26e3c53d41ec4093b23f0957766cd0cbdab70/f454db6d64120c946ae6700bcf4b4b6ea1bef26c`
and `20e26e3c53d41ec4093b23f0957766cd0cbdab70/4f20bd2` are explicitly
rejected, not repaired or reinterpreted.

The 1,059 discovered-test result is an unproven claim to independently verify.
`FPCR-EXECUTE-020` owns exactly one serialized, hermetic root-CI execution,
bounded to 2,700 seconds.  `FPCR-CROSS-030` may run alongside it after
discovery.  This reseal unlocks neither an original FPC node nor implementation,
fixture promotion, performance/GCO work, or a knowledge BASELINE retry.

The runner rejects a bad source tuple before it can perform discovery or
execution.  All resulting receipts must bind the exact commit/tree pair and
preserve adverse evidence.  Any later change needs a separately sealed court.
