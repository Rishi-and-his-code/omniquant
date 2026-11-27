"""Shared helpers."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import numpy as np


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, default=_json_default, allow_nan=False)


def json_loads(s: str | None) -> Any:
    if s is None:
        return None
    return json.loads(s)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    if isinstance(obj, (np.integer,)):
        return int(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def sanitize_numbers(obj: Any) -> Any:
    """Recursively replace NaN/Inf with None for JSON safety."""
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: sanitize_numbers(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_numbers(v) for v in obj]
    return obj
