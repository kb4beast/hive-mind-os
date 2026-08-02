# Phase 5B installed-wheel receipt

## Local isolated-wheel verification

The Phase 5B candidate was built and installed into a clean target directory with the
local environment's setuptools 82.0.1 using `--no-build-isolation`. This is useful
package evidence but does not replace hosted construction with the repository-pinned
`setuptools==83.0.0`.

- Distribution: `hive-mind-os==0.6.0`
- Wheel: `hive_mind_os-0.6.0-py3-none-any.whl`
- Local wheel SHA-256:
  `6f3c561cf714e5cc8fcc3bdb997f02cc136f47c9fe5f1c83f4b15b43414608da`
- Phase 5B verification JSON SHA-256:
  `0a011b0c2e028e65d8d7fc938527d07b71ed3ec1bc9e5a77cc76a5d68f07b316`
- Phase 5A verification JSON remained:
  `73c1f76efb9683e6673f11cca376881f283374cfec0d7be0cd34dc765bca91ee`
- Governed JSON resources: 133
- Components: 22
- Architect contracts: 13
- Typed outputs: 10
- Design options: 2
- Effective capabilities: 0
- Tools: 0
- Authority: `none`
- Activation: `inert`
- Provisional option: `option:modular-inert`
- Higher-score blocked option: `option:monolithic-active`
- Selection status: `defer`
- Handoff: `curator`

The verifier confirmed exact request and output scope, complete contract validation,
viability-before-score ranking, positive and exactly reconciled rollback/verification
reserves, and false selection, implementation, risk-acceptance, budget, and activation
authorization.

## Hosted requirement

The terminal receipt still requires exact-head hosted construction with setuptools
83.0.0, the Python 3.11/3.12/3.14 matrix, Ruff, Pyright, CodeQL, secret scanning,
dependency/license review, SPDX 2.3 SBOM, artifact retention, and push-event provenance
where available. No hosted terminal or provenance claim is made here.
