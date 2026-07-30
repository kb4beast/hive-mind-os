# Phase 4B installed-wheel receipt

- implementation commit: `e00b017`
- build command: `python -m pip wheel --no-deps --wheel-dir <temporary> .`
- build isolation: enabled from pinned `pyproject.toml` requirements
- wheel: `hive_mind_os-0.6.0-py3-none-any.whl`
- wheel digest:
  `sha256:d4f955bf2781abdad8e02e971bd2111f1636fb11daf971fa416babf7b7b341e5`
- installation: clean temporary `pip --target`, `--no-deps`
- installed JSON resources: `133`
- installed successor digest:
  `sha256:0494c32237fbbe83b90444c9b0496646e8f0b27e7c20379320a6bd7241697463`
- installed activation: `inert`
- installed authority: `none`
- installed public: `false`

The unavailable `python -m build` frontend was replaced by pip's PEP 517 wheel
frontend. Both invoke the pinned setuptools build backend in isolation. Temporary
wheel and installation directories were deleted after verification.
