"""Claude API client with robust error handling."""

import asyncio
import json
import logging
from typing import Optional
from datetime import date
from dataclasses import dataclass, field

import anthropic
from pydantic import BaseModel, ValidationError

from ...models.policy import Policy, PolicyType
from .prompts import POLICY_ANALYSIS_PROMPT

logger = logging.getLogger(__name__)


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================


class LLMError(Exception):
    """Base class for LLM-related errors."""

    def __init__(self, message: str, url: str = "", recoverable: bool = True):
        super().__init__(message)
        self.url = url
        self.recoverable = recoverable


class LLMParseError(LLMError):
    """Error parsing LLM response (JSON or validation)."""

    def __init__(self, message: str, raw_response: str = "", url: str = ""):
        super().__init__(message, url=url, recoverable=True)
        self.raw_response = raw_response


class LLMContextTooLongError(LLMError):
    """Content exceeds model's context window."""

    def __init__(self, message: str, url: str = "", content_length: int = 0):
        super().__init__(message, url=url, recoverable=True)
        self.content_length = content_length


class LLMRateLimitError(LLMError):
    """Rate limit exceeded - should wait and retry."""

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message, recoverable=True)
        self.retry_after = retry_after


class LLMAuthError(LLMError):
    """Authentication failed - cannot recover."""

    def __init__(self, message: str):
        super().__init__(message, recoverable=False)


class LLMServiceError(LLMError):
    """Service unavailable or overloaded."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message, recoverable=True)
        self.status_code = status_code


# =============================================================================
# ERROR STATISTICS
# =============================================================================


@dataclass
class LLMErrorStats:
    """Track error statistics for diagnostics."""

    parse_errors: int = 0
    validation_errors: int = 0
    rate_limit_errors: int = 0
    context_too_long_errors: int = 0
    connection_errors: int = 0
    timeout_errors: int = 0
    service_errors: int = 0
    auth_errors: int = 0
    other_errors: int = 0
    total_retries: int = 0
    urls_with_errors: list = field(default_factory=list)

    @property
    def total_errors(self) -> int:
        return (
            self.parse_errors
            + self.validation_errors
            + self.rate_limit_errors
            + self.context_too_long_errors
            + self.connection_errors
            + self.timeout_errors
            + self.service_errors
            + self.auth_errors
            + self.other_errors
        )

    def record_error(self, error_type: str, url: str = "") -> None:
        """Record an error occurrence."""
        attr = f"{error_type}_errors"
        if hasattr(self, attr):
            setattr(self, attr, getattr(self, attr) + 1)
        else:
            self.other_errors += 1
        if url and url not in self.urls_with_errors:
            self.urls_with_errors.append(url)

    def summary(self) -> dict:
        """Get summary for logging."""
        return {
            "total": self.total_errors,
            "parse": self.parse_errors,
            "validation": self.validation_errors,
            "rate_limit": self.rate_limit_errors,
            "context_too_long": self.context_too_long_errors,
            "connection": self.connection_errors,
            "timeout": self.timeout_errors,
            "service": self.service_errors,
            "retries": self.total_retries,
        }


# =============================================================================
# RESPONSE MODEL
# =============================================================================


class PolicyAnalysis(BaseModel):
    is_relevant: bool
    relevance_score: int
    relevance_explanation: str
    policy_name: Optional[str] = None
    jurisdiction: Optional[str] = None
    policy_type: str = "unknown"
    summary: Optional[str] = None
    effective_date: Optional[str] = None
    key_requirements: Optional[str] = None
    bill_number: Optional[str] = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _coerce_types(data: dict) -> dict:
    """Coerce common type mismatches from LLM responses.

    Claude sometimes returns strings where we expect other types,
    especially when processing non-English content.
    """
    result = data.copy()

    # Coerce is_relevant to bool
    if "is_relevant" in result:
        val = result["is_relevant"]
        if isinstance(val, str):
            result["is_relevant"] = val.lower() in (
                "true", "yes", "1", "ja", "oui", "sí", "是", "да", "sim"
            )
        elif isinstance(val, (int, float)):
            result["is_relevant"] = bool(val)

    # Coerce relevance_score to int
    if "relevance_score" in result:
        val = result["relevance_score"]
        if isinstance(val, str):
            try:
                # Handle "8/10", "8", "8.0", "8 out of 10" formats
                val = val.split("/")[0].split(" ")[0].strip()
                result["relevance_score"] = int(float(val))
            except (ValueError, IndexError):
                result["relevance_score"] = 0
        elif isinstance(val, float):
            result["relevance_score"] = int(val)

    # Clamp relevance_score to valid range
    if "relevance_score" in result:
        score = result["relevance_score"]
        if isinstance(score, int):
            result["relevance_score"] = max(0, min(10, score))

    # Normalize null-like values to None
    null_values = (
        None, "null", "None", "N/A", "n/a", "", "unknown", "Unknown",
        "nicht verfügbar", "non disponible", "不明", "ei saatavilla",
        "não disponível", "недоступно", "不适用", "該当なし"
    )
    for key in ["policy_name", "jurisdiction", "summary", "effective_date",
                "key_requirements", "bill_number", "relevance_explanation"]:
        if key in result:
            val = result[key]
            if val in null_values:
                if key == "relevance_explanation":
                    result[key] = "No explanation provided"
                else:
                    result[key] = None

    # Ensure relevance_explanation exists
    if "relevance_explanation" not in result or not result["relevance_explanation"]:
        result["relevance_explanation"] = "No explanation provided"

    return result


def _extract_json(text: str) -> str:
    """Extract JSON from Claude's response, handling various formats."""
    # Try markdown code blocks first
    if "```json" in text:
        try:
            return text.split("```json")[1].split("```")[0].strip()
        except IndexError:
            pass

    if "```" in text:
        try:
            return text.split("```")[1].split("```")[0].strip()
        except IndexError:
            pass

    # Try to find JSON object directly
    text = text.strip()
    if text.startswith("{"):
        # Find matching closing brace
        depth = 0
        for i, char in enumerate(text):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[: i + 1]

    return text


def _get_retry_after(error: anthropic.RateLimitError) -> Optional[float]:
    """Extract retry-after value from rate limit error."""
    try:
        if hasattr(error, "response") and error.response:
            headers = error.response.headers
            if "retry-after" in headers:
                return float(headers["retry-after"])
    except (ValueError, AttributeError):
        pass
    return None


# =============================================================================
# CLAUDE CLIENT
# =============================================================================


class ClaudeClient:
    """Async Claude API client with comprehensive error handling."""

    # Retry configuration
    MAX_RETRIES = 3
    BASE_DELAY = 1.0  # seconds
    MAX_DELAY = 30.0  # seconds

    # Context limits (conservative estimates)
    MAX_CONTENT_CHARS = 45000  # Leave room for prompt template

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

        # Track usage stats
        self.call_count = 0
        self.tokens_input = 0
        self.tokens_output = 0

        # Track errors
        self.error_stats = LLMErrorStats()

    async def analyze_policy(
        self,
        content: str,
        url: str,
        language: Optional[str] = None,
    ) -> PolicyAnalysis:
        """Analyze page content for policy information.

        Args:
            content: Page text content
            url: Source URL
            language: Detected language code

        Returns:
            PolicyAnalysis with extracted information

        Raises:
            LLMParseError: If response cannot be parsed
            LLMAuthError: If authentication fails (not recoverable)
            LLMRateLimitError: If rate limited (after retries exhausted)
            LLMContextTooLongError: If content too long (after truncation failed)
            LLMServiceError: If service unavailable (after retries exhausted)
        """
        # Truncate content if too long
        if len(content) > self.MAX_CONTENT_CHARS:
            content = content[: self.MAX_CONTENT_CHARS]
            logger.debug(f"Truncated content to {self.MAX_CONTENT_CHARS} chars for {url}")

        last_error = None
        delay = self.BASE_DELAY

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return await self._call_api(content, url, language)

            except anthropic.AuthenticationError as e:
                # Auth errors are not recoverable
                self.error_stats.record_error("auth", url)
                raise LLMAuthError(f"Authentication failed: {e}") from e

            except anthropic.RateLimitError as e:
                self.error_stats.record_error("rate_limit", url)
                retry_after = _get_retry_after(e) or delay
                if attempt < self.MAX_RETRIES:
                    self.error_stats.total_retries += 1
                    logger.warning(
                        f"Rate limited for {url}, waiting {retry_after:.1f}s "
                        f"(attempt {attempt}/{self.MAX_RETRIES})"
                    )
                    await asyncio.sleep(retry_after)
                    delay = min(delay * 2, self.MAX_DELAY)
                else:
                    raise LLMRateLimitError(
                        f"Rate limit exceeded after {self.MAX_RETRIES} retries",
                        retry_after=retry_after,
                    ) from e

            except anthropic.BadRequestError as e:
                # Check if it's a context length error
                error_msg = str(e).lower()
                if "context" in error_msg or "token" in error_msg or "length" in error_msg:
                    self.error_stats.record_error("context_too_long", url)
                    # Try with shorter content
                    if len(content) > 10000:
                        content = content[:10000]
                        logger.warning(
                            f"Context too long for {url}, retrying with truncated content"
                        )
                        self.error_stats.total_retries += 1
                        continue
                    raise LLMContextTooLongError(
                        f"Content too long even after truncation: {e}",
                        url=url,
                        content_length=len(content),
                    ) from e
                else:
                    # Other bad request error
                    self.error_stats.record_error("other", url)
                    raise LLMError(f"Bad request: {e}", url=url) from e

            except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
                error_type = "timeout" if isinstance(e, anthropic.APITimeoutError) else "connection"
                self.error_stats.record_error(error_type, url)
                if attempt < self.MAX_RETRIES:
                    self.error_stats.total_retries += 1
                    logger.warning(
                        f"{error_type.title()} error for {url}, retrying in {delay:.1f}s "
                        f"(attempt {attempt}/{self.MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, self.MAX_DELAY)
                    last_error = e
                else:
                    raise LLMServiceError(
                        f"{error_type.title()} error after {self.MAX_RETRIES} retries: {e}"
                    ) from e

            except (
                anthropic.InternalServerError,
                anthropic.APIStatusError,
            ) as e:
                status = getattr(e, "status_code", 0)
                self.error_stats.record_error("service", url)
                if attempt < self.MAX_RETRIES:
                    self.error_stats.total_retries += 1
                    logger.warning(
                        f"Service error ({status}) for {url}, retrying in {delay:.1f}s "
                        f"(attempt {attempt}/{self.MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, self.MAX_DELAY)
                    last_error = e
                else:
                    raise LLMServiceError(
                        f"Service error after {self.MAX_RETRIES} retries: {e}",
                        status_code=status,
                    ) from e

            except LLMParseError:
                # Parse errors - don't retry, just raise
                raise

            except Exception as e:
                # Unexpected error
                self.error_stats.record_error("other", url)
                logger.error(f"Unexpected error for {url}: {type(e).__name__}: {e}")
                raise LLMError(f"Unexpected error: {e}", url=url) from e

        # Should not reach here, but just in case
        if last_error:
            raise LLMServiceError(f"Failed after {self.MAX_RETRIES} retries") from last_error
        raise LLMError("Failed for unknown reason", url=url)

    async def _call_api(
        self,
        content: str,
        url: str,
        language: Optional[str],
    ) -> PolicyAnalysis:
        """Make the actual API call and parse response."""
        prompt = POLICY_ANALYSIS_PROMPT.format(
            url=url,
            language=language or "Unknown",
            content=content,
        )

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )

        # Track usage
        self.call_count += 1
        if hasattr(response, "usage"):
            self.tokens_input += response.usage.input_tokens
            self.tokens_output += response.usage.output_tokens

        raw_text = response.content[0].text

        # Extract JSON from response
        try:
            json_text = _extract_json(raw_text)
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            self.error_stats.record_error("parse", url)
            logger.error(
                f"JSON parse error for {url}: {e}\n"
                f"Raw response (first 500 chars): {raw_text[:500]}"
            )
            raise LLMParseError(
                f"Invalid JSON: {e}",
                raw_response=raw_text[:1000],
                url=url,
            )

        # Coerce types to handle common LLM response variations
        data = _coerce_types(data)

        # Validate with Pydantic
        try:
            return PolicyAnalysis(**data)
        except ValidationError as e:
            self.error_stats.record_error("validation", url)
            error_details = []
            for err in e.errors():
                field = ".".join(str(loc) for loc in err["loc"])
                msg = err["msg"]
                got = err.get("input", "N/A")
                if isinstance(got, str) and len(got) > 100:
                    got = got[:100] + "..."
                error_details.append(f"{field}: {msg} (got: {got!r})")

            error_summary = "; ".join(error_details)
            logger.error(
                f"Validation error for {url}:\n"
                f"  Errors: {error_summary}\n"
                f"  Parsed data keys: {list(data.keys())}"
            )
            raise LLMParseError(
                f"Validation failed: {error_summary}",
                raw_response=json.dumps(data, default=str, ensure_ascii=False)[:1000],
                url=url,
            )

    def to_policy(
        self,
        analysis: PolicyAnalysis,
        url: str,
        language: str,
    ) -> Optional[Policy]:
        """Convert PolicyAnalysis to Policy model."""
        if not analysis.is_relevant or not analysis.policy_name:
            return None

        effective_date = None
        if analysis.effective_date:
            try:
                effective_date = date.fromisoformat(analysis.effective_date)
            except ValueError:
                pass

        try:
            policy_type = PolicyType(analysis.policy_type)
        except ValueError:
            policy_type = PolicyType.UNKNOWN

        return Policy(
            url=url,
            policy_name=analysis.policy_name,
            jurisdiction=analysis.jurisdiction or "Unknown",
            policy_type=policy_type,
            summary=analysis.summary or "",
            relevance_score=analysis.relevance_score,
            effective_date=effective_date,
            source_language=language,
            bill_number=analysis.bill_number,
            key_requirements=analysis.key_requirements,
        )

    def get_error_summary(self) -> dict:
        """Get error statistics summary."""
        return self.error_stats.summary()

    async def close(self) -> None:
        """Close the client."""
        await self.client.close()
