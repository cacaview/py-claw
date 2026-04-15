"""
VCR (Video Cassette Recorder) service for test fixture management.

VCR records API responses to fixture files and replays them during tests,
providing deterministic test runs without real API calls.

Based on the TypeScript vcr.ts implementation.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, TypeVar

from py_claw.services.vcr.types import (
    VCRConfig,
    Recording,
    StreamingRecording,
    TokenCountRecording,
    get_vcr_config,
    should_use_vcr,
    _get_cwd,
    _get_config_home,
    _hash_input,
    _get_fixtures_root,
)

T = TypeVar("T")

# Global cost tracking for session
_total_cached_cost: float = 0.0


def _normalize_path(s: str) -> str:
    """Normalize paths in a string for cross-platform fixture compatibility."""
    config = get_vcr_config()
    cwd = _get_cwd()
    config_home = _get_config_home()

    result = s
    # Replace paths with placeholders
    result = result.replace(config_home, config.config_home_placeholder)
    result = result.replace(cwd, config.cwd_placeholder)

    # Normalize backslashes to forward slashes for cross-platform
    result = result.replace("\\", "/")

    # Replace timestamps
    timestamp_re = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
    result = re.sub(timestamp_re, "[TIMESTAMP]", result)

    # Replace UUIDs
    uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    result = re.sub(uuid_pattern, "[UUID]", result, flags=re.IGNORECASE)

    # Replace counts
    result = re.sub(r'num_files="\d+"', 'num_files="[NUM]"', result)
    result = re.sub(r'duration_ms="\d+"', 'duration_ms="[DURATION]"', result)
    result = re.sub(r'cost_usd="\d+"', 'cost_usd="[COST]"', result)

    return result


def _hydrate_value(s: str) -> str:
    """Restore normalized values back to actual values (for playback)."""
    cwd = _get_cwd()
    config_home = _get_config_home()

    result = s
    # Restore placeholders to actual values
    result = result.replace("[NUM]", "1")
    result = result.replace("[DURATION]", "100")
    result = result.replace("[CONFIG_HOME]", config_home)
    result = result.replace("[CWD]", cwd)

    return result


async def with_fixture(
    input_data: Any,
    fixture_name: str,
    func: Callable[[], Any],
) -> Any:
    """Generic fixture management helper.

    Handles caching, reading, writing fixtures for any data type.

    Args:
        input_data: Input data to create fixture key from
        fixture_name: Name for the fixture file
        func: Function to call if no cached fixture exists

    Returns:
        The result from cache or func()
    """
    if not should_use_vcr():
        return await _maybe_await(func())

    config = get_vcr_config()

    # Create hash of input for fixture filename
    json_data = json.dumps(input_data, sort_keys=True, ensure_ascii=True)
    hash_str = hashlib.sha1(json_data.encode()).hexdigest()[:12]

    fixtures_root = _get_fixtures_root()
    fixture_dir = os.path.join(fixtures_root, "fixtures")
    filename = os.path.join(fixture_dir, f"{fixture_name}-{hash_str}.json")

    # Try to read cached fixture
    try:
        with open(filename, "r", encoding="utf-8") as f:
            cached = json.load(f)
        return cached
    except (FileNotFoundError, json.JSONDecodeError) as e:
        if isinstance(e, FileNotFoundError):
            pass  # Fixture doesn't exist, we'll create it
        else:
            raise

    # Check if we're in CI and fixture is missing
    is_ci = os.environ.get("CI", "").lower() in ("1", "true", "yes")
    vcr_record = os.environ.get("VCR_RECORD", "").lower() in ("1", "true", "yes")

    if is_ci and not vcr_record and not config.force_record:
        raise RuntimeError(
            f"Fixture missing: {filename}. Re-run tests with VCR_RECORD=1, then commit the result."
        )

    # Create & write new fixture
    result = await _maybe_await(func())

    os.makedirs(fixture_dir, exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return result


async def with_vcr(
    messages: list[dict[str, Any]],
    func: Callable[[], Any],
) -> Any:
    """VCR wrapper for API calls with messages.

    Records API responses to fixtures and replays them.

    Args:
        messages: List of messages to send to API
        func: Function to call if no cached fixture exists

    Returns:
        API response from cache or func()
    """
    if not should_use_vcr():
        return await _maybe_await(func())

    config = get_vcr_config()

    # Normalize messages for hashing
    dehydrated = _dehydrate_messages(messages)

    # Create fixture filename based on message hashes
    hashes = []
    for msg in dehydrated:
        msg_json = json.dumps(msg, sort_keys=True, ensure_ascii=True)
        h = hashlib.sha1(msg_json.encode()).hexdigest()[:6]
        hashes.append(h)

    fixtures_root = _get_fixtures_root()
    fixture_dir = os.path.join(fixtures_root, "fixtures")
    filename = os.path.join(fixture_dir, f"{'-'.join(hashes)}.json")

    # Try to read cached fixture
    try:
        with open(filename, "r", encoding="utf-8") as f:
            cached = json.load(f)
        return cached.get("output", [])
    except (FileNotFoundError, json.JSONDecodeError):
        pass  # Fixture doesn't exist

    # Check if we're in CI and fixture is missing
    is_ci = os.environ.get("CI", "").lower() in ("1", "true", "yes")
    vcr_record = os.environ.get("VCR_RECORD", "").lower() in ("1", "true", "yes")

    if is_ci and not vcr_record and not config.force_record:
        raise RuntimeError(
            f"API fixture missing: {filename}. Re-run tests with VCR_RECORD=1."
        )

    # Create & write new fixture
    results = await _maybe_await(func())

    # Don't record in CI unless explicitly requested
    if is_ci and not vcr_record:
        return results

    os.makedirs(fixture_dir, exist_ok=True)
    output = {
        "input": dehydrated,
        "output": results,
        "recorded_at": _get_timestamp(),
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return results


def _dehydrate_messages(messages: list[dict[str, Any]]) -> list[Any]:
    """Dehydrate messages by normalizing dynamic values."""
    result = []
    for msg in messages:
        dehydrated = _deep_dehydrate(msg)
        result.append(dehydrated)
    return result


def _deep_dehydrate(obj: Any) -> Any:
    """Recursively dehydrate an object."""
    if isinstance(obj, str):
        return _normalize_path(obj)
    elif isinstance(obj, dict):
        return {k: _deep_dehydrate(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_deep_dehydrate(item) for item in obj]
    else:
        return obj


def _deep_hydrate(obj: Any) -> Any:
    """Recursively hydrate an object."""
    if isinstance(obj, str):
        return _hydrate_value(obj)
    elif isinstance(obj, dict):
        return {k: _deep_hydrate(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_deep_hydrate(item) for item in obj]
    else:
        return obj


def _get_timestamp() -> str:
    """Get current ISO timestamp."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


async def with_token_count_vcr(
    messages: Any,
    tools: Any,
    func: Callable[[], int | None],
) -> int | None:
    """VCR wrapper for token counting.

    Args:
        messages: Messages to count tokens for
        tools: Tools schema
        func: Function to call if no cached fixture exists

    Returns:
        Token count from cache or func()
    """
    config = get_vcr_config()

    # Dehydrate before hashing
    cwd_slug = re.sub(r"[^a-zA-Z0-9]", "-", _get_cwd())
    dehydrated = _deep_dehydrate(json.dumps({"messages": messages, "tools": tools}))
    dehydrated_str = json.dumps(dehydrated, sort_keys=True)
    dehydrated_str = dehydrated_str.replace(cwd_slug, "[CWD_SLUG]")

    # Replace UUIDs
    dehydrated_str = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "[UUID]",
        dehydrated_str,
        flags=re.IGNORECASE,
    )

    result = await with_fixture(
        dehydrated_str,
        "token-count",
        func,
    )
    return result.get("tokenCount")


async def with_streaming_vcr(
    messages: list[dict[str, Any]],
    func: Callable[[], AsyncGenerator[Any, None]],
) -> AsyncGenerator[Any, None]:
    """VCR wrapper for streaming API calls with messages.

    Records streaming responses to fixtures and replays them.

    Args:
        messages: List of messages to send to API
        func: Async generator function to call if no cached fixture exists

    Yields:
        Streaming response events from cache or func()
    """
    if not should_use_vcr():
        async for event in func():
            yield event
        return

    config = get_vcr_config()

    # Normalize messages for hashing
    dehydrated = _dehydrate_messages(messages)

    # Create fixture filename based on message hashes
    hashes = []
    for msg in dehydrated:
        msg_json = json.dumps(msg, sort_keys=True, ensure_ascii=True)
        h = hashlib.sha1(msg_json.encode()).hexdigest()[:6]
        hashes.append(h)

    fixtures_root = _get_fixtures_root()
    fixture_dir = os.path.join(fixtures_root, "fixtures")
    filename = os.path.join(fixture_dir, f"{'-'.join(hashes)}.stream.json")

    # Try to read cached fixture
    try:
        with open(filename, "r", encoding="utf-8") as f:
            cached = json.load(f)

        events = cached.get("events", [])
        for event in events:
            yield event
        return
    except (FileNotFoundError, json.JSONDecodeError):
        pass  # Fixture doesn't exist

    # Check if we're in CI and fixture is missing
    is_ci = os.environ.get("CI", "").lower() in ("1", "true", "yes")
    vcr_record = os.environ.get("VCR_RECORD", "").lower() in ("1", "true", "yes")

    if is_ci and not vcr_record and not config.force_record:
        raise RuntimeError(
            f"Streaming fixture missing: {filename}. Re-run tests with VCR_RECORD=1."
        )

    # Collect events from the generator
    events: list[Any] = []
    cost_usd: float | None = None

    try:
        async for event in func():
            events.append(event)
            # Track cost if present
            if isinstance(event, dict):
                if event.get("type") == "usage" or "usage" in event:
                    usage = event.get("usage", event)
                    if isinstance(usage, dict):
                        cost_usd = usage.get("cost_usd")
    except Exception as e:
        # If streaming fails, yield the error
        yield {"type": "error", "error": str(e)}
        return

    # Don't record in CI unless explicitly requested
    if is_ci and not vcr_record:
        for event in events:
            yield event
        return

    # Write fixture
    os.makedirs(fixture_dir, exist_ok=True)
    output = {
        "events": events,
        "recorded_at": _get_timestamp(),
        "cached_cost_usd": cost_usd,
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Track cost
    if cost_usd is not None:
        add_cached_cost_to_total_session_cost(cost_usd)

    for event in events:
        yield event


def add_cached_cost_to_total_session_cost(cost_usd: float) -> None:
    """Track cached cost for session analytics.

    Adds the cost of a cached VCR response to the total session cost,
    which is used for analytics reporting.

    Args:
        cost_usd: The cost in USD from the cached response
    """
    global _total_cached_cost
    _total_cached_cost += cost_usd


def get_total_cached_cost() -> float:
    """Get the total cached cost for this session.

    Returns:
        Total cost in USD accumulated from cached responses
    """
    return _total_cached_cost


def reset_total_cached_cost() -> None:
    """Reset the total cached cost (for testing)."""
    global _total_cached_cost
    _total_cached_cost = 0.0


async def _maybe_await(val: Any) -> Any:
    """Await a value if it's a coroutine, otherwise return it."""
    import asyncio
    if asyncio.iscoroutine(val):
        return await val
    return val


def reset_vcr_for_testing() -> None:
    """Reset VCR state for testing."""
    from py_claw.services.vcr.types import _vcr_config
    global _vcr_config, _total_cached_cost
    _vcr_config = None
    _total_cached_cost = 0.0
