# Post-merge collector fixture repair

Builder identity: `/root/merge_fixture_builder`. Separate examiner:
`/root/merge_failure_examiner`. Independent candidate verification and the
delivery verdict are pending and must bind their actual reviewed commit.
The owner waived new preimplementation tournament gates; this record is not a
claim that a fresh tournament or independent promotion court ran.

Subject: main `0d161d869a9a717b891872fc9b8203ae07eae51f`, tree
`81d638986bf3553bdf2ebd45d224bd40a526fbc4`. The full failed
[CI run](https://github.com/kb4beast/hive-mind-os/actions/runs/34785092456)
is retained externally at `C:\h\postmerge-windows-20260913\ci-full.log`, with its
SHA-256 in SOURCE-INTAKE.json. Both Windows jobs failed the two timeout tests
at the mandatory sole-parent check. SOURCE-INTAKE.json also identifies the
original test source and unchanged production scripts. Repository sources
are MIT licensed; no external implementation was copied.

## Builder results and failed attempts

- `baseline-reproduction.log`: original two tests on the pinned merge subject,
  both fail at topology validation in 1.277 seconds. The baseline module was
  loaded from `git show` with its original repository file identity; edited
  fixture code was not substituted into this reproduction.
- `collector-312-bound.log`: all 14 tests pass, no skips, 61.275 seconds, with
  Python 3.12 parent and collector child resolution bound to the same interpreter
  directory through PATH. `python312-binding.log` and version log retain identity.
- `collector-314-bound.log`: all 14 tests pass, no skips, 60.360 seconds, with
  Python 3.14 parent and child resolution likewise bound; binding/version retained.
- `ruff.log`: repository check passes. `pyright.log`: zero errors, six existing
  warnings. No warning suppression or policy change was added.
- Initial `collector-312.log` fails the unrelated diagnostic test because the
  parent loader cannot import `hive_mind_os.activation_bundle` without candidate
  source on PYTHONPATH. Its failed import placeholder counted as one test while
  the correctly bound child ran 23 tests. The failure remains retained.
  `collector-312-source-path.log` passes after setting PYTHONPATH, but did not yet
  bind collector child resolution to Python 3.12. It is not a complete 3.12
  qualification. Initial `collector-314.log` also remains as a passing earlier
  attempt. The final bound logs above include the final script-copy assertions.

Final focused invocations set PATH to the matching interpreter directory first,
set PYTHONPATH to the candidate `src` and repository root, and run
`python -m unittest tests.test_collect_v4_activation_evidence -v`. Production
scripts did not change. Full current-main coverage and complete platform CI
remain separate delivery obligations; these focused results do not replace them.

## Atomic claims and scoped dispositions

The independent examiner supports adapting the timeout fixture to the pinned
candidate and rejects relaxing parent validation, skipping merge coverage,
accepting any nonzero exit, extending deadlines or changing push checkout to
hide the merge. EXAMINER.md preserves its evidence, alternatives and dissent;
EXAMINER-MANIFEST.json retains the original examination seal. The builder's
recommendation is **adapt** for this bounded fixture repair. Only an independent
reviewer may issue the candidate verdict; no builder self-judgment is implied.

The implementation retains every original assertion and adds an executable
synthetic merge case. It checks direct merge rejection, pinned nested candidate
and parent, copied current scripts, actual timeout receipt, disabled activation
and qualification, and unchanged outer HEAD. Architecture, threats, acceptance,
compatibility, migration and rollback are in
`docs/architecture/ADR-COLLECTOR-PINNED-TIMEOUT-FIXTURES.md`.

Dissent remains: the timeout fixture samples the historical candidate's first
modules, and cannot prove all current-main module behavior. Missing historical
objects still fail, rather than silently substituting a source. The synthetic
Git object is test-only and not a signed authority artifact. No runtime-node
completion, full lifecycle, superiority, independent key administration,
promotion, protected merge or deployment claim follows from this repair.
