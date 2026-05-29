"""
WO-027: Load external ReportBro JSON templates shipped with the claim module.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

_TEMPLATE_PACKAGE = "claim.reports.templates"


@lru_cache(maxsize=None)
def load_report_template(name: str) -> str:
    """Return the ReportBro template JSON for ``name`` (filename without .json)."""
    if not name or "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"Invalid report template name: {name!r}")
    resource = resources.files(_TEMPLATE_PACKAGE).joinpath(f"{name}.json")
    if not resource.is_file():
        raise FileNotFoundError(f"Report template not found: {name}")
    return resource.read_text(encoding="utf-8")
