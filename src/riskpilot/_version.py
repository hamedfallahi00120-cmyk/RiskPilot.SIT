"""Version resolution.

The version is defined only in ``pyproject.toml``; it is read back from the
installed distribution metadata at runtime so it is never duplicated in source
(H8). This module is a leaf: it imports nothing from :mod:`riskpilot`.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

__all__ = ["__version__"]


def _resolve() -> str:
    try:
        return _distribution_version("riskpilot-core")
    except PackageNotFoundError:  # pragma: no cover - only when running uninstalled
        return "0.0.0+unknown"


__version__ = _resolve()
