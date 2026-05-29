"""Feedback input normalization (WO-032)."""

from typing import Any, Dict


def normalize_feedback_input(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map legacy ``asessment`` key to ``assessment`` without DB schema changes."""
    if "asessment" in data and "assessment" not in data:
        data = dict(data)
        data["assessment"] = data.pop("asessment")
    elif "asessment" in data:
        data = dict(data)
        data.pop("asessment", None)
    return data
