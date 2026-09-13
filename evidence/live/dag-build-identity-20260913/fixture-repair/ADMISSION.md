# Fixture repair integrated into the build delivery

The full local gate for `dac56971058a746a22fcad9bef92751ce456fdb7` ran
1,776 tests: one error, eleven skips. The sole error was Git clone exit 128 in
`test_non_stage_zero_index_is_rejected`, before that test's index assertion.
The complete gate streams and receipt are retained in the sibling
`failed-local-qualification/` directory. Python's displayed CalledProcessError
did not include captured Git stderr, so this record does not claim the exact
missing-lock cause was established for that local failure.

The failing helper uses the same local object-directory copying mechanism as
the independently reproduced fixture race in PR179. Integrate that reviewed
fixture correction verbatim from commit
`3bfd4edd504a1c1dc6b4448941dc38f4fdfcdbba`: normal Git transport, explicit
authenticated historical source, private-metadata isolation and cold-history
regressions. The test file is byte-identical to that source candidate. All 457
original assertion calls remain; no retries, accepted error codes, skipped
checks or maintenance suppression are introduced.

SOURCE-COPY-MANIFEST.json binds exact copies of PR179's failed CI evidence,
rejected intermediate repair, independent objection and resolution. Paths in
those original records describe their original location. Their relative
manifests resolve under these preserved directories. The build identity code
and its new acceptance tests remain unchanged from the independently reviewed
candidate. This integration still requires its own final independent review,
complete local gate and exact-head CI; earlier receipts are not rewritten.

Product schemas and runtime authority are unchanged. Revert this bounded
test-fixture integration to roll back while retaining the failure evidence.
