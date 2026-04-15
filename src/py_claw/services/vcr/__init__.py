"""
VCR (Video Cassette Recorder) test fixture service.

Records API responses to fixture files and replays them during tests.
"""
from __future__ import annotations

from py_claw.services.vcr.types import (
    VCRConfig,
    Recording,
    StreamingRecording,
    TokenCountRecording,
    get_vcr_config,
    set_vcr_config,
    should_use_vcr,
)

from py_claw.services.vcr.service import (
    with_fixture,
    with_vcr,
    with_streaming_vcr,
    with_token_count_vcr,
    add_cached_cost_to_total_session_cost,
    get_total_cached_cost,
    reset_total_cached_cost,
    reset_vcr_for_testing,
)

__all__ = [
    "VCRConfig",
    "Recording",
    "StreamingRecording",
    "TokenCountRecording",
    "get_vcr_config",
    "set_vcr_config",
    "should_use_vcr",
    "with_fixture",
    "with_vcr",
    "with_streaming_vcr",
    "with_token_count_vcr",
    "add_cached_cost_to_total_session_cost",
    "get_total_cached_cost",
    "reset_total_cached_cost",
    "reset_vcr_for_testing",
]
