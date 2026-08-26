"""Tests for RDA-036 retry and error classification."""

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import ValidationError

from app.services.workflow.retry_handler import RetryHandler, RetryPolicy
from app.services.workflow.state import ErrorSeverity, WorkflowError, WorkflowStage


def _error(severity: ErrorSeverity, retryable: bool = True) -> WorkflowError:
    return WorkflowError(
        error_id=uuid.uuid4(), stage=WorkflowStage.SEARCH, message="failure",
        severity=severity, timestamp=datetime.now(UTC), retryable=retryable,
    )


def test_classify_common_errors() -> None:
    handler = RetryHandler()
    assert handler.classify_error(asyncio.TimeoutError()) == ErrorSeverity.TRANSIENT
    assert handler.classify_error(ValidationError.from_exception_data("x", [])) == ErrorSeverity.VALIDATION
    response = httpx.Response(429, request=httpx.Request("GET", "https://example.test"))
    assert handler.classify_error(httpx.HTTPStatusError("rate", request=response.request, response=response)) == ErrorSeverity.TRANSIENT
    response = httpx.Response(500, request=httpx.Request("GET", "https://example.test"))
    assert handler.classify_error(httpx.HTTPStatusError("down", request=response.request, response=response)) == ErrorSeverity.PROVIDER


def test_is_retryable_uses_severity_and_flag() -> None:
    handler = RetryHandler()
    assert handler.is_retryable(_error(ErrorSeverity.TRANSIENT)) is True
    assert handler.is_retryable(_error(ErrorSeverity.PROVIDER)) is True
    assert handler.is_retryable(_error(ErrorSeverity.PERMANENT)) is False
    assert handler.is_retryable(_error(ErrorSeverity.TRANSIENT, retryable=False)) is False


def test_retry_uses_exponential_backoff_and_stops_at_max_attempts() -> None:
    asyncio.run(_test_retry_uses_exponential_backoff_and_stops_at_max_attempts())


async def _test_retry_uses_exponential_backoff_and_stops_at_max_attempts() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=1, exponential_base=2)
    handler = RetryHandler(policy)
    operation = AsyncMock(side_effect=asyncio.TimeoutError("timeout"))

    with patch("asyncio.sleep", new_callable=AsyncMock) as sleep:
        with pytest.raises(asyncio.TimeoutError):
            await handler.execute_with_retry(operation)

    assert operation.await_count == 3
    assert handler.last_retry_count == 2
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]


def test_permanent_error_is_not_retried() -> None:
    asyncio.run(_test_permanent_error_is_not_retried())


async def _test_permanent_error_is_not_retried() -> None:
    handler = RetryHandler()
    operation = AsyncMock(side_effect=ValueError("invalid DOI"))

    with patch("asyncio.sleep", new_callable=AsyncMock) as sleep:
        with pytest.raises(ValueError):
            await handler.execute_with_retry(operation)

    assert operation.await_count == 1
    sleep.assert_not_awaited()


def test_retry_succeeds_after_transient_failure() -> None:
    asyncio.run(_test_retry_succeeds_after_transient_failure())


async def _test_retry_succeeds_after_transient_failure() -> None:
    handler = RetryHandler()
    operation = AsyncMock(side_effect=[asyncio.TimeoutError(), "ok"])

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await handler.execute_with_retry(operation)

    assert result == "ok"
    assert handler.last_retry_count == 1