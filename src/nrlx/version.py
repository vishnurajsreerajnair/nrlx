"""The version of nrlx, set in pyproject.toml and read back from the installed
package


"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("nrlx")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
