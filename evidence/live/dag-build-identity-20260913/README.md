# DAG build identity repair evidence

This delivery addresses `PUBLIC-RUNTIME-500-EXPECTED-IDENTITY-BUILD-001` only.
The immutable baseline is commit `b19b2a177e2d10ebf49b565dcdd1ad9878bbaeac`,
tree `6fb9b59c4c697ae9b9bc296676783f8ce662f3c0` (repository MIT license).

- `selection/` preserves the independent recommendation, considered alternatives,
  dissent, and static mapping of all twenty V4 nodes to exact baseline Git blobs.
  Its mapping does not claim that tests ran or that current nodes are accepted.
- `baseline/` preserves the independent fifteen-case executable reproduction,
  input/output artifacts, exact source hashes, first harness setup failure, and
  a parameterized reproduction script. Four CLI mismatch cases incorrectly
  created or replaced output; the service rejected unsupported keywords.
- Each original manifest binds the original artifact bytes. Absolute paths in
  those historical records describe their original location. The copies here
  retain their exact bytes under repository evidence attributes. Relative names
  under `baseline/` resolve within that directory; original selection file
  basenames resolve within `selection/`.

The code repair forwards the two optional expectations through the existing
canonical validator before output handling. Added CLI/service acceptance matrices
cover absent and existing outputs, replacement, each mismatched or malformed
identity, malformed plan digest, matching identities, and omitted expectations.
Existing concurrency, no-overwrite, substitution and inert-execution tests remain.
No schema migration is needed; rollback is an ordinary revert. This is input
constraint enforcement, not caller authentication or runtime activation.

The owner waived the preimplementation tournament. The independent recommendation
and reproduction are evidence of selection and the defect, not a newly fabricated
court verdict. Delivery review and CI are attached to the resulting PR's immutable
candidate. No superiority or full-node completion is claimed. Generic guide repair,
current-generation accepted receipts, independent host custody/signatures, and
promotion activation remain separate obligations.
