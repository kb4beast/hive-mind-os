# hive-cortex autonomy benchmark

A reproducible, offline, toolchain-free benchmark over the four
`tests/fixtures/hive_cortex/` scenarios, plus a comparator court that cannot
express anything above a recorded measurement.

## Layout

| File | Role |
|---|---|
| `scenarios.json` | One entry per fixture: required roles, the patch a lane may apply, and a pure-Python checker program. |
| `runner.py` | Scenario loading, the two lanes, the recovery drill, the seven metrics, seeded statistics, rendering, and the CLI. |
| `comparator_court.py` | Comparator provenance records, the measurement-capped verdict, and the results-document claim guard. |
| `comparators.json` | The comparator registry. Every entry is either pinned **and** licensed, or marked `unavailable` with a reason. |

## Reproduction

```bash
PYTHONPATH=src python benchmarks/hive-cortex/runner.py \
    --output <output-dir> --seed 7 --repetitions 3 \
    --render docs/benchmarks/HIVE_CORTEX_RESULTS.md
```

`PYTHONPATH=src` is required: the runner imports
`hive_mind_os.benchmark_harness` for `MEASUREMENT_DISPOSITION` and
`bootstrap_interval`. `<output-dir>` must live outside the repository tree —
run outputs are regenerable evidence and are not committed. A run refuses to
overwrite an existing `run_id` directory; evidence is append-only.

## The seven measured dimensions

`correctness`, `human_interventions`, `role_coverage`, `recovery`,
`evidence_completeness`, `cost_units`, `latency_seconds`. Every attempt records
all seven in `metrics.json`. `latency_seconds` is informational and excluded
from `results_digest`, which is taken over `raw-results.digest-input.jsonl`.
That copy zeroes every `latency_seconds` **and** substitutes the sha256 each
`metrics.json` would carry at zero latency — the file itself embeds the measured
latency, so without the second substitution the digest would still drift between
identical runs. Every other dimension stays digest-bound.

Each attempt directory retains four artifacts — `lane-report.json`,
`metrics.json`, `check.json`, `checkpoint.json` — whether the attempt passed or
failed. Nothing is deleted on failure.

## Recovery drill

Repetition 1 records an uninterrupted workspace digest. On repetition 2 the
lane is run twice: once interrupted immediately after it writes its checkpoint,
then again with `resume=True` in the same workspace. `recovery` is true when the
post-resume workspace digest equals repetition 1's. Repetitions 1 and 3+ inherit
that drill result for the same scenario and lane.

## Loading convention

This directory is intentionally **not** a Python package. The hyphen in
`hive-cortex` makes it unimportable by module path, and no `__init__.py` may be
added. Load the modules by file path:

```python
import importlib.util
import sys
from pathlib import Path

_BENCH = Path("benchmarks/hive-cortex")


def _load(alias: str, filename: str):
    spec = importlib.util.spec_from_file_location(alias, _BENCH / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module  # required before exec_module for dataclasses
    spec.loader.exec_module(module)
    return module


runner = _load("hive_cortex_runner", "runner.py")
court = _load("hive_cortex_comparator_court", "comparator_court.py")
```

Registering the module in `sys.modules` before `exec_module` is not optional:
`dataclasses` resolves field types through `sys.modules[cls.__module__]` and
raises `AttributeError` for a module that was never registered.

## No-claims rule

The court's only disposition is
`hive_mind_os.benchmark_harness.MEASUREMENT_DISPOSITION`; any other value raises
`SuperiorityClaimError`. No external comparator has been executed here, so no
external entry carries a pin or a license — inventing either would be the exact
failure this node exists to prevent. `guard_results_document` rejects
comparative phrasing in the rendered results document and requires the
disclaimer line verbatim, and `--render` refuses to write a document that fails
the guard.
