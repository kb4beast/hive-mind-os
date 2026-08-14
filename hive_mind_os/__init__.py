"""Source-checkout loader that rejects foreign editable-install precedence.

The distributable package remains under ``src/hive_mind_os``.  This lightweight
checkout package makes a bare ``python -m unittest`` resolve that local source
tree even when the shared interpreter has another Git worktree installed in
editable mode.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SOURCE_PACKAGE = (Path(__file__).resolve().parents[1] / "src" / "hive_mind_os").resolve()
_SOURCE_INIT = _SOURCE_PACKAGE / "__init__.py"
if not _SOURCE_INIT.is_file():
    raise ImportError(f"local Hive Mind OS source package is missing: {_SOURCE_INIT}")

_SOURCE_SPEC = importlib.util.spec_from_file_location(
    __name__,
    _SOURCE_INIT,
    submodule_search_locations=[str(_SOURCE_PACKAGE)],
)
if _SOURCE_SPEC is None or _SOURCE_SPEC.loader is None:
    raise ImportError(f"cannot load local Hive Mind OS package: {_SOURCE_INIT}")

# Replace every import/resource-location attribute, not merely ``__path__``.
# ``importlib.resources`` consults the loader and module spec, so leaving the
# shim's original SourceFileLoader installed would direct schema reads back to
# this directory even though Python modules came from ``src``.
__file__ = str(_SOURCE_INIT)
__loader__ = _SOURCE_SPEC.loader
__package__ = __name__
__path__ = [str(_SOURCE_PACKAGE)]
__spec__ = _SOURCE_SPEC
_SOURCE_SPEC.loader.exec_module(sys.modules[__name__])
