"""Restricted ``__builtins__`` for executing mesh2cad-generated build123d scripts."""

from __future__ import annotations

import builtins as _builtins
from typing import Any


def _limited_import(
    name: str,
    globals: dict[str, Any] | None = None,
    locals: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> Any:
    root = name.split(".", 1)[0]
    if root != "build123d":
        raise ImportError(
            f"import of {name!r} is not allowed in generated CAD scripts (only 'build123d' is permitted)."
        )
    return _builtins.__import__(name, globals, locals, fromlist, level)


def cad_script_safe_builtins() -> dict[str, Any]:
    """Builtins for generated scripts: deny high-risk names, replace ``__import__``."""
    deny = frozenset(
        {
            "eval",
            "exec",
            "compile",
            "open",
            "input",
            "breakpoint",
            "__import__",
            "quit",
            "exit",
        }
    )
    out: dict[str, Any] = {}
    for name in dir(_builtins):
        if name.startswith("_") or name in deny:
            continue
        out[name] = getattr(_builtins, name)
    out["__import__"] = _limited_import
    return out
