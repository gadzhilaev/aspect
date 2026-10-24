"""Unified per-user-turn budget for the agent loop (no HTTP/DB I/O)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class LoopStopReason(str, Enum):
    """Internal stop — not a successful final answer."""

    budget_exhausted = "budget_exhausted"
    context_limit = "context_limit"
    timeout = "timeout"
    invalid_action = "invalid_action"
    no_progress = "no_progress"
    provider_daily_budget = "provider_daily_budget"


class BudgetExhausted(RuntimeError):
    def __init__(self, reason: LoopStopReason, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(detail or reason.value)


# Named defaults (literals — do not read from a slots dataclass attribute).
DEFAULT_MAX_MODEL_HTTP = 4
DEFAULT_MAX_TOOL_CALLS = 3
DEFAULT_MAX_REPAIRS = 1  # format OR citation — shared
DEFAULT_TIMEOUT_S = 90.0
DEFAULT_MAX_RESULT_CHARS = 4000
DEFAULT_MAX_TRANSCRIPT_CHARS = 12_000
DEFAULT_MAX_RAW_ACTION_CHARS = 24_000


@dataclass(frozen=True, slots=True)
class BudgetDefaults:
    """Snapshot of protocol defaults (for docs / Settings alignment)."""

    max_model_http: int = DEFAULT_MAX_MODEL_HTTP
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS
    max_repairs: int = DEFAULT_MAX_REPAIRS
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_result_chars: int = DEFAULT_MAX_RESULT_CHARS
    max_transcript_chars: int = DEFAULT_MAX_TRANSCRIPT_CHARS
    max_raw_action_chars: int = DEFAULT_MAX_RAW_ACTION_CHARS


@dataclass(frozen=True, slots=True)
class TurnBudgetConfig:
    max_model_http: int = DEFAULT_MAX_MODEL_HTTP
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS
    max_repairs: int = DEFAULT_MAX_REPAIRS
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_result_chars: int = DEFAULT_MAX_RESULT_CHARS
    max_transcript_chars: int = DEFAULT_MAX_TRANSCRIPT_CHARS
    max_raw_action_chars: int = DEFAULT_MAX_RAW_ACTION_CHARS

    def __post_init__(self) -> None:
        if self.max_model_http < 1:
            raise ValueError("max_model_http must be >= 1")
        if self.max_tool_calls < 0:
            raise ValueError("max_tool_calls must be >= 0")
        if self.max_repairs < 0:
            raise ValueError("max_repairs must be >= 0")
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be > 0")
        if self.max_result_chars < 1 or self.max_transcript_chars < 1:
            raise ValueError("size limits must be >= 1")
        if self.max_raw_action_chars < 1:
            raise ValueError("max_raw_action_chars must be >= 1")


@dataclass
class ModelAttemptLease:
    """Returned after reserving a model attempt slot (spent immediately).

    Reservation is **not** the same as an HTTP transport call. Call
    ``TurnBudget.mark_transport_started`` only when the HTTP client begins
    the request. A pre-send size/context failure must not reserve a slot.
    """

    attempt_index: int
    remaining_timeout_s: float
    is_repair: bool = False
    # True when this was the last remaining model slot **before** spend —
    # only ``final`` is a complete outcome after this attempt.
    final_only: bool = False


@dataclass
class TurnBudget:
    """Independent of transport. Clock injectable for tests (monotonic).

    Accounting (stage 4.6.1):
    - ``model_http_reserved`` / ``model_http_used``: attempt slots spent via
      ``begin_model_attempt`` (after payload fits). Not refunded after start.
    - ``model_http_transport``: actual HTTP client calls that began.
    - ``model_http_responses``: responses received (any status / parse).
    - ``transcript_chars``: size of the **current** prepared payload (not a
      cumulative sum across attempts).
    """

    config: TurnBudgetConfig = field(default_factory=TurnBudgetConfig)
    clock: Callable[[], float] = field(default=time.monotonic)
    _started_at: float = field(init=False)
    model_http_used: int = 0
    model_http_transport: int = 0
    model_http_responses: int = 0
    tool_calls_used: int = 0
    repairs_used: int = 0
    transcript_chars: int = 0
    peak_payload_chars: int = 0
    stop_reason: LoopStopReason | None = None

    def __post_init__(self) -> None:
        self._started_at = self.clock()

    # --- time ---

    def elapsed_s(self) -> float:
        return max(0.0, self.clock() - self._started_at)

    def remaining_timeout_s(self) -> float:
        return max(0.0, float(self.config.timeout_s) - self.elapsed_s())

    def check_deadline(self) -> None:
        if self.remaining_timeout_s() <= 0:
            self.stop_reason = LoopStopReason.timeout
            raise BudgetExhausted(LoopStopReason.timeout, "turn deadline exceeded")

    # --- model HTTP ---

    @property
    def model_http_remaining(self) -> int:
        return max(0, self.config.max_model_http - self.model_http_used)

    @property
    def model_http_reserved(self) -> int:
        """Alias: reserved attempt slots (== model_http_used after begin)."""
        return self.model_http_used

    def can_begin_model_attempt(self, *, as_repair: bool = False) -> bool:
        if self.stop_reason is not None:
            return False
        if self.remaining_timeout_s() <= 0:
            return False
        if self.model_http_remaining < 1:
            return False
        if as_repair and self.repairs_used >= self.config.max_repairs:
            return False
        return True

    def begin_model_attempt(self, *, as_repair: bool = False) -> ModelAttemptLease:
        """Reserve a model attempt slot **after** payload prep succeeded.

        Call only when the prepared payload fits and a transport send will
        follow. Slot is spent immediately and is **not** refunded on timeout /
        401 / 429 / 5xx / invalid response after the request has begun.
        """
        self.check_deadline()
        if as_repair and self.repairs_used >= self.config.max_repairs:
            self.stop_reason = LoopStopReason.budget_exhausted
            raise BudgetExhausted(
                LoopStopReason.budget_exhausted, "repair budget exhausted"
            )
        if self.model_http_remaining < 1:
            self.stop_reason = LoopStopReason.budget_exhausted
            raise BudgetExhausted(
                LoopStopReason.budget_exhausted, "model HTTP budget exhausted"
            )
        # Capture final-only **before** spending the last slot (no off-by-one).
        final_only = self.model_http_remaining == 1
        self.model_http_used += 1
        if as_repair:
            self.repairs_used += 1
        remaining = self.remaining_timeout_s()
        if remaining <= 0:
            self.stop_reason = LoopStopReason.timeout
            raise BudgetExhausted(LoopStopReason.timeout, "no time left for request")
        return ModelAttemptLease(
            attempt_index=self.model_http_used,
            remaining_timeout_s=remaining,
            is_repair=as_repair,
            final_only=final_only,
        )

    def mark_transport_started(self) -> None:
        """Record that an HTTP client call actually began (not a size check)."""
        self.model_http_transport += 1

    def mark_transport_response(self) -> None:
        """Record that a transport response body was received."""
        self.model_http_responses += 1

    def provisional_lease_fields(self, *, as_repair: bool = False) -> dict[str, object]:
        """Budget fields for payload prep **without** spending a slot."""
        remaining_slots = self.model_http_remaining
        return {
            "remaining_timeout_s": self.remaining_timeout_s(),
            "final_only": remaining_slots == 1,
            "attempt_index": self.model_http_used + 1,
            "is_repair": as_repair,
            "model_http_remaining_before": remaining_slots,
        }

    # --- final-only / tools ---

    def allows_tool_request(self) -> bool:
        """tool_request needs ≥1 HTTP now and ≥1 HTTP left after for result→model."""
        self.check_deadline()
        # After this attempt would be used, need at least one more for continuation.
        # Caller reserves attempt separately; here we require remaining >= 2.
        return self.model_http_remaining >= 2 and self.tool_calls_remaining >= 1

    def is_final_only_mode(self) -> bool:
        """Last model attempt available: only ``final`` is a complete turn outcome."""
        return self.model_http_remaining == 1 and self.tool_calls_remaining >= 0

    @property
    def tool_calls_remaining(self) -> int:
        return max(0, self.config.max_tool_calls - self.tool_calls_used)

    def begin_tool_call(self) -> int:
        self.check_deadline()
        if self.tool_calls_remaining < 1:
            self.stop_reason = LoopStopReason.budget_exhausted
            raise BudgetExhausted(
                LoopStopReason.budget_exhausted, "tool call budget exhausted"
            )
        self.tool_calls_used += 1
        return self.tool_calls_used

    def check_prepared_payload_chars(self, n: int) -> None:
        """Per-attempt serialized size of the prepared payload.

        Does **not** accumulate across attempts (that falsely exhausted the
        turn after a few tool steps). A failed check is ``context_limit`` and
        must happen **before** ``begin_model_attempt``.
        """
        if n < 0:
            raise ValueError("chars must be >= 0")
        self.transcript_chars = n
        self.peak_payload_chars = max(self.peak_payload_chars, n)
        if n > self.config.max_transcript_chars:
            self.stop_reason = LoopStopReason.context_limit
            raise BudgetExhausted(
                LoopStopReason.context_limit,
                "prepared payload exceeds context limit",
            )

    def record_transcript_chars(self, n: int) -> None:
        """Backward-compatible alias → ``check_prepared_payload_chars``."""
        self.check_prepared_payload_chars(n)

    def mark_no_progress(self, detail: str = "") -> None:
        self.stop_reason = LoopStopReason.no_progress
        raise BudgetExhausted(LoopStopReason.no_progress, detail or "no_progress")

    def mark_invalid_action(self, detail: str = "") -> None:
        self.stop_reason = LoopStopReason.invalid_action
        raise BudgetExhausted(LoopStopReason.invalid_action, detail or "invalid_action")

    def mark_provider_daily_budget(self, detail: str = "") -> None:
        self.stop_reason = LoopStopReason.provider_daily_budget
        raise BudgetExhausted(
            LoopStopReason.provider_daily_budget,
            detail or "provider_daily_budget",
        )

    def snapshot(self) -> dict[str, object]:
        return {
            "model_http_used": self.model_http_used,
            "model_http_reserved": self.model_http_reserved,
            "model_http_transport": self.model_http_transport,
            "model_http_responses": self.model_http_responses,
            "model_http_remaining": self.model_http_remaining,
            "tool_calls_used": self.tool_calls_used,
            "tool_calls_remaining": self.tool_calls_remaining,
            "repairs_used": self.repairs_used,
            "repairs_remaining": max(0, self.config.max_repairs - self.repairs_used),
            "remaining_timeout_s": self.remaining_timeout_s(),
            "transcript_chars": self.transcript_chars,
            "peak_payload_chars": self.peak_payload_chars,
            "final_only": self.is_final_only_mode(),
            "allows_tool_request": (
                self.model_http_remaining >= 2 and self.tool_calls_remaining >= 1
            ),
            "stop_reason": self.stop_reason.value if self.stop_reason else None,
        }
