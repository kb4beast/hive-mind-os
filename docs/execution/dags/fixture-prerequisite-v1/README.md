# fixture-prerequisite-v1

This sealed, eight-node, Judge-authorized DAG evaluates one narrow prerequisite: whether a new, hermetic and ephemeral fixture support surface can clear the sole remaining root-CI fixture API failure at baseline `b789b68e7d6a741e0b85a3ac33cbce846e1e32c9`.

It is not authority to revive or reuse rejected fixture candidate `41950b74bdec2b6e1c48ee7f5ef3ce947d0c8378`, promote GCO candidate `d02c2d206246c11939d1c9bde7714d46c02c26ec`, alter doctor performance evidence, or retry knowledge `BASELINE-000`.

The sealed causality predicate is a fresh editable-install virtual environment (`PYTHONNOUSERSITE=1`, cleared `PYTHONPATH`, `-E -s`) whose import resolves under repository `src/hive_mind_os`, then runs `python -m unittest discover -s tests -v`: exactly 1050 tests, eight skips, and only `test_autopilot_fixture_seed.FixtureSeedAPISurfaceTests.test_future_fixture_api_is_available`, caused by absent `ContentAddressedFixtureSeed`, `FixtureIntegrityError`, and `FixturePolicyError`.

Compile only to the ignored state file, then lint and print rounds:

```powershell
python docs/execution/dags/fixture-prerequisite-v1/generate_plan.py
python docs/execution/dags/fixture-prerequisite-v1/verify_plan.py
python .autopilot/bin/autopilot.py --repo-root . dag-lint --plan .autopilot/state/fixture-prerequisite-v1.json --strict --json
python .autopilot/bin/autopilot.py --repo-root . dag-rounds --plan .autopilot/state/fixture-prerequisite-v1.json --max-sessions 4 --actor codex:fixture-prerequisite --json
```

Rounds are: seal; causality plus independent tests; architecture; build; independent curation; four-way integration; distinct judgment. Every worker has one isolated branch and retained unsquashed commit; one Integrator serializes each round. All fixture data is local, content-verified, invocation-scoped, and cleaned; persistent caches/daemons/shared objects/alternates/hardlinks/symlinks/junctions/network and ambient Git authority are forbidden.
