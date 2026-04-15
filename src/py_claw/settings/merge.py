from __future__ import annotations

from copy import deepcopy
from typing import Any
from collections.abc import Mapping


def merge_settings(*values: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for value in values:
        if value:
            merged = _merge_pair(merged, value)
    return merged


def _merge_pair(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        existing = result.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            result[key] = _merge_pair(dict(existing), value)
        else:
            result[key] = deepcopy(value)
    return result
