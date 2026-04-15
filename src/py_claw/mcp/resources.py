from __future__ import annotations

from typing import Any


_RESOURCE_FIELDS = ("uri", "name", "description", "mimeType", "text", "blob")


def extract_result_payload(response: Any) -> Any:
    if isinstance(response, dict) and isinstance(response.get("result"), dict):
        return response["result"]
    return response


def extract_error_payload(response: Any) -> dict[str, Any] | None:
    if not isinstance(response, dict):
        return None
    error = response.get("error")
    return error if isinstance(error, dict) else None


def normalize_resource_list(response: Any) -> list[dict[str, Any]]:
    payload = extract_result_payload(response)
    if not isinstance(payload, dict):
        return []
    resources = payload.get("resources")
    if not isinstance(resources, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in resources:
        resource = _normalize_record(item)
        if resource is not None:
            normalized.append(resource)
    return normalized


def normalize_resource_contents(response: Any) -> list[dict[str, Any]]:
    payload = extract_result_payload(response)
    if not isinstance(payload, dict):
        return []
    contents = payload.get("contents")
    if not isinstance(contents, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in contents:
        content = _normalize_record(item)
        if content is not None:
            normalized.append(content)
    return normalized


def _normalize_record(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    normalized = {field: value[field] for field in _RESOURCE_FIELDS if isinstance(value.get(field), str)}
    if not isinstance(normalized.get("uri"), str) or not normalized["uri"]:
        return None
    return normalized
