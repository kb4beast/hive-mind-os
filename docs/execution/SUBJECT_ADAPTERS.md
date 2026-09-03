# Subject and Resource Adapter Contract

Status: V3 candidate contract for `ADAPTER-INDEX-210`.

Hive Mind OS treats a repository as one subject kind, not as the definition of
a subject. `SubjectDescriptor` uses the same identity contract for repositories,
artifacts, sources, datasets, APIs, tickets, databases, workflows, and custom
subjects. Every descriptor binds its locator, required capabilities, authority
digest, and provenance. `SubjectSnapshot` then binds that stable identity to one
immutable, evidence-backed, point-in-time content digest. A mutable observation
is not accepted as a snapshot.

Resources are typed independently. `ResourceDescriptor` covers repository
paths, artifacts, sources, datasets, APIs, tickets, databases, workflows, and
custom resources. Mutable resources require an exact version. Network locators
must use HTTPS without embedded credentials; local locators must be relative and
cannot escape the subject. `ConservativeResourceAdapter` accepts bounded bytes
only long enough to check size, detect secret-like material, and compute a
digest. The resulting `ResourceSnapshot` contains no body.

`AdapterRegistry` is the sole selection surface. A registration binds adapter
identity, exact implementation digest, subject kinds, capabilities, required
authority, provenance, privilege rank, vendor, and independent-validation
status. A third-party registration without independent validation is rejected
and remains inert. Re-registering identical bytes is idempotent; substituting a
different registration under the same ID fails closed.

Selection requires its own evidence and a non-conflicting
`CapabilityAuthority`. Requested and adapter-required capabilities must all be
allowed and none may be denied. Candidates are sorted by lowest privilege,
fewest unused capabilities, vendor neutrality, and canonical adapter ID. The
selection receipt binds the complete registry digest, so adding or replacing a
candidate cannot masquerade as the prior decision. Selection returns data; it
does not invoke an implementation or grant effect authority.

## V1 claim dispositions

| Source row | Disposition | Executable evidence |
|---|---|---|
| `V1-ADAPTER-INDEX-210-OBJ` | Adapt | Subject/resource contracts, registry, and exact-snapshot index are separate, composable modules. |
| `V1-ADAPTER-INDEX-210-AC-01` | Adapt | `SubjectKind` and `ResourceKind` represent repository and non-repository subjects through one interface. |
| `V1-ADAPTER-INDEX-210-AC-02` | Adopt fail-closed invariant | Registry selection is deterministic, lowest-sufficient, evidence-bound, and checks allowed/denied authority. |
| `V1-ADAPTER-INDEX-210-AC-03` | Adapt | Index identity binds subject snapshot, analyzer, environment, and every content digest. |
| `V1-ADAPTER-INDEX-210-AC-04` | Adopt security invariant | The conservative adapter rejects secrets, unsafe links, and oversized bodies and persists metadata only. |
| `V1-ADAPTER-INDEX-210-AC-05` | Adopt fail-closed invariant | Unregistered adapters are unreachable and unvalidated third-party registrations are rejected. |

Rollback removes the V3 adapter/index modules and invalidates their selection
and index receipts. It does not delete retained provenance or rejection
evidence.
