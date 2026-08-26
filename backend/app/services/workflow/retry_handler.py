"""Retry policy and error classification for workflow operations."""

import asyncio
import inspect
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, RateLimitError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.services.workflow.state import ErrorSeverity, WorkflowError, WorkflowStage


class RetryPolicy(BaseModel):
    """Configurable retry policy for one external operation."""

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=3, ge=1)
    base_delay_seconds: float = Field(default=1.0, ge=0)
    max_delay_seconds: float = Field(default=30.0, ge=0)
    exponential_base: float = Field(default=2.0, ge=1)
    retryable_severities: list[ErrorSeverity] = Field(
        default_factory=lambda: [ErrorSeverity.TRANSIENT, ErrorSeverity.PROVIDER]
    )

    @model_validator(mode="after")
    def validate_delays(self) -> "RetryPolicy":
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must be at least base_delay_seconds")
        return self


class RetryHandler:
    """Execute operations with bounded exponential-backoff retries."""

    def __init__(self, policy: RetryPolicy | None = None) -> None:
        self.policy = policy or RetryPolicy()
        self.last_attempts = 0
        self.last_retry_count = 0
        self.last_error: Exception | None = None
        self.last_severity: ErrorSeverity | None = None

    def classify_error(self, exception: Exception) -> ErrorSeverity:
        """Classify common network, provider and validation failures."""
        if isinstance(exception, (asyncio.TimeoutError, httpx.TimeoutException, APITimeoutError)):
            return ErrorSeverity.TRANSIENT
        if isinstance(exception, (httpx.HTTPStatusError, APIStatusError)):
            if exception.response.status_code == 429:
                return ErrorSeverity.TRANSIENT
            return ErrorSeverity.PROVIDER
        if isinstance(exception, (RateLimitError, APIConnectionError)):
            return ErrorSeverity.TRANSIENT
        if isinstance(exception, APIError):
            return ErrorSeverity.PROVIDER
        if isinstance(exception, ValidationError):
            return ErrorSeverity.VALIDATION
        return ErrorSeverity.PERMANENT

    def is_retryable(
        self, error: WorkflowError, policy: RetryPolicy | None = None
    ) -> bool:
        """Return whether a recorded error is eligible for another attempt."""
        active_policy = policy or self.policy
        return error.retryable and error.severity in active_policy.retryable_severities

    async def execute_with_retry(
        self,
        func: Callable[..., Any],
        *args: Any,
        policy: RetryPolicy | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute ``func`` and retry eligible failures with exponential backoff."""
        active_policy = policy or self.policy
        self.last_attempts = 0
        self.last_retry_count = 0
        self.last_error = None
        self.last_severity = None

        for attempt in range(active_policy.max_attempts):
            self.last_attempts = attempt + 1
            try:
                result = func(*args, **kwargs)
                return await result if inspect.isawaitable(result) else result
            except Exception as exception:
                severity = self.classify_error(exception)
                self.last_error = exception
                self.last_severity = severity
                error = WorkflowError(
                    error_id=uuid.uuid4(),
                    stage=WorkflowStage.IDLE,
                    message=str(exception),
                    severity=severity,
                    timestamp=datetime.now(UTC),
                    retryable=severity in active_policy.retryable_severities,
                )
                can_retry = self.is_retryable(error, active_policy)
                if not can_retry or attempt + 1 >= active_policy.max_attempts:
                    raise
                delay = min(
                    active_policy.base_delay_seconds
                    * (active_policy.exponential_base**attempt),
                    active_policy.max_delay_seconds,
                )
                self.last_retry_count += 1
                await asyncio.sleep(delay)

        raise RuntimeError("retry loop exited unexpectedly")