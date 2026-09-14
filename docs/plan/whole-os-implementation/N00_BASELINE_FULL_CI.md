# N00 baseline full-CI execution receipt

Status: **PASS; local unsealed execution evidence**

- Candidate commit: `7dff0a807936b5be33099bdaa5c242674c624776`
- Candidate role: accepted N00 reconciliation on top of handoff `3dc87ad0749ee468ed7ceab779d92c9446248b7e`
- Observed completion time: `2026-09-14T03:31:54.0229811Z`
- Host: `Windows-11-10.0.26200-SP0`
- Python: `3.14.4` at `C:\Python314\python.exe`
- Working tree after the run: clean before this receipt was added

The shell bound `PYTHONPATH` to this worktree's absolute `src` directory and
asserted that `hive_mind_os.__file__` resolved under that directory before
running the required gate:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
python -c "import hive_mind_os; assert hive_mind_os.__file__.startswith($env:PYTHONPATH)"
python -m unittest discover -s tests -v
```

Observed result:

```text
Ran 1825 tests in 2416.681s

OK (skipped=12)
```

The skips were reported as platform/environment capability limitations,
including unavailable Windows symlink privileges. The run also emitted
existing `ResourceWarning` and deprecation warnings without test failures.

This record does not contain or claim a signed transcript digest. It is an
Orchestrator observation of the local command result and establishes baseline
health only. It is not reusable as qualification for N01/N02 or a later
integrated candidate because those candidate bytes differ.
