# Hive Mind OS

> **Don't trust your coding agent. Verify it.**

**For developers and teams shipping AI-authored code, Hive Mind OS produces a
tamper-evident receipt bundle proving what an agent actually did — the commands it
ran, their exit codes, the diff it produced, and whether an independently sealed
check passed — unlike CI, which runs only after you've decided to trust the change,
and unlike agent frameworks, which orchestrate work but prove nothing.**

## Start in 60 seconds

Run the offline demonstration from a checkout:

```bash
python -m pip install --no-deps -e .
hive-mind demo
```

The demo creates a temporary repository with a known regression, repairs it, and
writes a receipt bundle to `./demo-out`. It prints the repair result, the Curator's
independent sealed-check result, and the location of the bundle.

`demo` uses the deterministic `fixture-demo` backend. It knows only the bundled
fixture layout; it does **not** inspect or repair an arbitrary repository. The output
directory must not already exist.

## Status: early. Here is exactly what works.

| Capability | Status |
|---|---|
| Verify a local agent-authored change against sealed checks (`hive-mind verify`) | Works offline and deterministically |
| See a complete deterministic fixture delivery (`hive-mind demo`) | Works offline; not a general coding agent |
| Real model drives the change (`--backend model`) | Not ready for routine use |
| Remote push / pull requests | Local Git only |
| Production use | Prototype release only; no production use or user validation |

## Verify an existing change

To verify the latest commit in a local repository, provide an executable acceptance
specification that was sealed before the candidate change:

```bash
hive-mind verify \
  --repository /path/to/local/repository \
  --spec /path/to/acceptance-spec.json \
  --output /path/to/absent/receipt-bundle
```

The specification must declare the complete set of paths changed by that commit in
`declared_paths`. A successful run writes the evidence bundle; a failed validation
does not publish one.

For field-by-field guidance, see [Write an acceptance
specification](docs/ACCEPTANCE_SPECIFICATION_GUIDE.md).

For a complete offline walkthrough that creates a local Git repository, commits an
agent-authored patch, and inspects the resulting verification bundle, see
[Verify an agent-authored change](examples/verify-an-agent-change/README.md).

## Architecture

Hive Mind OS is an evidence-driven operating-system prototype for autonomous product
and software delivery. Its target architecture has eight independent specialist
roles. The local repository-delivery workflow currently executes Explorer, Builder,
and Curator; the other roles are planned.

| Agent | Status | Responsibility |
|---|---|---|
| Orchestrator | Planned | Sets direction, decomposes outcomes, and manages risk, budgets, recovery, and dependencies |
| Explorer | Implemented | Reproduces the repository failure through a typed test capability |
| Architect | Planned | Designs scalable, secure, evolvable solutions with explicit threats and rollback |
| Builder | Implemented | Creates a branch, writes the change, tests it, and commits it locally |
| Curator | Implemented | Independently re-executes sealed checks against the candidate delivery |
| Integrator | Planned | Connects systems, data, repositories, and workflows through stable contracts |
| Steward | Planned | Maintains reliability, dependencies, code health, observability, and recoverability |
| Optimizer | Planned | Measures outcomes, teaches validated lessons, and promotes proven improvements |

The delivery workflow binds model use, a policy boundary, budgets, a local Git adapter,
and a Curator that reruns sealed checks in a separate local workspace. On success it
publishes a reversible bundle containing a patch, manifest, validated receipt store,
and machine-readable mission report. It does not yet support remote delivery,
durable resume, hostile-code isolation, or routine model-driven changes.

## Evidence, courtroom, and source records

The evidence model is deliberately detailed. Its courtroom process, source dockets,
architecture decisions, and known release blockers live in the architecture records:

- [Courtroom synthesis](docs/architecture/COURTROOM_SYNTHESIS.md) — decisions, dissent, evidence burdens, and appeals.
- [Conglomerated system](docs/architecture/CONGLOMERATED_SYSTEM.md) — target architecture and replaceable boundaries.
- [Hardened vision contract](docs/architecture/HARDENED_VISION_CONTRACT.md) — machine-checkable product constraints.
- [Source-docket record](src/hive_mind_os/founding_docket.py) and [additional-video docket](docs/architecture/ADDITIONAL_VIDEO_DOCKET.md) — preserved source and claim inventory.
- [Foundation plan](docs/architecture/FOUNDATION_PLAN.md) and [active implementation roadmap](docs/plan/00_OVERVIEW.md) — staged implementation and blockers.

The project does not claim production readiness, complete source ingestion, hard
hostile-code isolation, or superiority over other systems. Those claims require
independent evidence and reproducible evaluation.

## More commands and development details

`hive-mind deliver --backend fixture-demo` runs the same limited fixture backend
against its expected fixture layout. `hive-mind deliver --backend model` is opt-in,
but remains experimental; its provider configuration is documented in the
[model-adapter plan](docs/plan/P02_MODEL_ADAPTER.md).

For a current-state evidence artifact, run:

```bash
hive-mind audit --output evidence/audits/current-state.json
```

The repository CI gate is:

```bash
python -m unittest discover -s tests -v
```

See [AGENTS.md](AGENTS.md) for the governing delivery and evidence rules.
