# P13 Benchmark Court Results

- Run: `p13-19083f235b2820d7`
- Disposition: `measurement-recorded`
- Corpus digest: `sha256:b0f69a4465e4a3dd2ff35a9341d5ce34827181e4a952ea889c226182064dd62b`
- Code commit: `a2669a874c00633d986df8f078cf4b841555cbc1`
- Repetitions: 3
- Seed: 7

| Lane | Attempts | Success rate | Seeded bootstrap 95% CI |
|---|---:|---:|---:|
| baseline | 15 | 0.600 | [0.333, 0.800] |
| hive-mind | 15 | 0.400 | [0.133, 0.667] |

## Per-task measurements

### baseline

| Task | Attempts | Success rate | Seeded bootstrap 95% CI |
|---|---:|---:|---:|
| dependency-free-refactor | 3 | 0.000 | [0.000, 0.000] |
| doc-code-drift | 3 | 1.000 | [1.000, 1.000] |
| failing-test-fix | 3 | 1.000 | [1.000, 1.000] |
| missing-edge-case | 3 | 1.000 | [1.000, 1.000] |
| off-by-one-green-tests | 3 | 0.000 | [0.000, 0.000] |

### hive-mind

| Task | Attempts | Success rate | Seeded bootstrap 95% CI |
|---|---:|---:|---:|
| dependency-free-refactor | 3 | 0.000 | [0.000, 0.000] |
| doc-code-drift | 3 | 1.000 | [1.000, 1.000] |
| failing-test-fix | 3 | 1.000 | [1.000, 1.000] |
| missing-edge-case | 3 | 0.000 | [0.000, 0.000] |
| off-by-one-green-tests | 3 | 0.000 | [0.000, 0.000] |

These are measurements from one scripted task family and one in-repository baseline. They authorize no comparative quality or superiority claim.
Raw results and every failed attempt are retained under `evidence/benchmarks/p13-19083f235b2820d7/`.

## Required next evidence

- Multiple pinned external comparators.
- Multiple benchmark families and declared safety floors.
- Independent reproduction before any higher-burden court.
