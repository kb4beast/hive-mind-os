# Exact-Snapshot Subject Index

Status: V3 candidate contract for `ADAPTER-INDEX-210`.

`RepositoryIndexer` is named for its first consumer, but it accepts any
`SubjectSnapshot`. Its output identity covers:

- the stable subject identity and exact subject snapshot;
- the analyzer ID, version, implementation digest, and configuration digest;
- the exact environment digest;
- each resource identity, resource snapshot, content digest, byte length,
  conservative language label, analysis digest, and evidence references; and
- explicit reused, changed, and deleted resource IDs.

Entries are sorted by resource ID and contain no source body. Language metadata
is inferred from a closed extension table; unknown formats remain `unknown` and
are never executed to discover their type. Secret-like filenames are rejected.
The resource adapter has already rejected secret-like bodies, unsafe links, and
oversized inputs before an index can be built.

The in-process analysis cache key is exactly `(content_digest,
analyzer_digest, environment_digest)`. An unchanged blob under the same analyzer
and environment reuses its analysis. A changed blob, analyzer, or environment
produces a new analysis. Every new subject snapshot still produces new entries
bound to that snapshot even when their analysis digests are reusable. Resources
missing from the next exact snapshot appear in `deleted_resource_ids`; nothing
silently remains current.

A previous index from another subject is rejected. Duplicate resource IDs,
unprovenanced requests, mutable subject snapshots, malformed digests, and
ambiguous identities all fail closed. The cache is an optimization only: the
immutable index digest and its evidence remain the authority for reuse.

Rollback removes index code and invalidates dependent reuse receipts. Historical
index identities, deleted-resource records, adapter rejection evidence, and
source-license obligations remain retained.
