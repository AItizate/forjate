"""Importable view of scripts/wiki-compile.py.

The compiler is named with a hyphen so it reads as a command, which makes it
un-importable. This shim loads it by path so wiki-lint.py can reuse discover()
instead of duplicating the traversal rules.
"""

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "wiki_compile", Path(__file__).resolve().parent / "wiki-compile.py"
)
_mod = importlib.util.module_from_spec(_spec)
# dataclasses resolves annotations through sys.modules, so register first.
sys.modules["wiki_compile"] = _mod
_spec.loader.exec_module(_mod)

REPO = _mod.REPO
WIKI = _mod.WIKI
discover = _mod.discover
rel = _mod.rel
