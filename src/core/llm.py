"""Two-stage Claude LLM client: Haiku screening + Sonnet analysis."""

import asyncio
import json
import logging
from datetime import date
from typing import Optional

import anthropic
from pydantic import ValidationError

from .models import (
    Policy, PolicyType, PolicyAnalysis, ScreeningResult, CostInfo,
)

logger = logging.getLogger(__name__)

# --- Prompts ---

SCREENING_PROMPT = """Quick relevance check. Does this page describe government POLICY about:
- Data center waste heat reuse/recovery
- Data center energy efficiency requirements
- District heating involving data centers
- Heat recovery mandates or incentives for data centers
- Energy performance reporting requirements for data centers
- Cost-benefit analysis requirements for waste heat utilization
- Tax incentives or exemptions for heat recovery or district heating
- Energy efficiency directives applicable to data centers (e.g. EU EED)

Note: Content may be in any language (EN, DE, FR, SV, DA, NO, FI, IS, etc.).

URL: {url}

CONTENT (first 5000 chars):
{content}

RESPOND WITH JSON ONLY (no explanation):
{{"relevant": true/false, "confidence": 1-10}}
"""

ANALYSIS_PROMPT = """
Analyze this government web page for data center heat reuse policy information.

URL: {url}
Language: {language}

CONTENT:
{content}

TASK:
1. Determine if this describes a policy related to:
   - Data center waste heat / heat reuse
   - Energy efficiency requirements for data centers
   - District heating with data centers
   - Heat recovery mandates or incentives
   - Energy performance reporting requirements for data centers
   - Cost-benefit analysis requirements for waste heat utilization
   - Tax incentives or exemptions for heat recovery or district heating
   - Energy efficiency directives applicable to data centers (e.g. EU EED Article 26)

   The content may be in any language. Look for policy substance regardless of language.

2. If relevant, extract:
   - Policy name/title (in original language if not English)
   - Jurisdiction (country/region)
   - Type (law/regulation/directive/incentive/grant/plan)
   - Brief summary (2-3 sentences)
   - Effective date (if stated)
   - Key requirements

3. Rate relevance 1-10:
   - 1-3: Not relevant
   - 4-6: Tangentially relevant
   - 7-8: Relevant
   - 9-10: Highly relevant (specifically about data center heat reuse)

4. Extract referenced legislation:
   - List any bill numbers, law names, directive references, or related policies mentioned
   - List any URLs linking to other relevant policy documents

RESPOND WITH JSON ONLY:
{{
    "is_relevant": true/false,
    "relevance_score": 1-10,
    "relevance_explanation": "Brief explanation",
    "policy_name": "Name or null",
    "jurisdiction": "Country/region or null",
    "policy_type": "law|regulation|directive|incentive|grant|plan|unknown",
    "summary": "2-3 sentences or null",
    "effective_date": "YYYY-MM-DD or null",
    "key_requirements": "Key points or null",
    "bill_number": "Number or null",
    "referenced_policies": ["Related law/directive names or empty list"],
    "referenced_urls": ["URLs to related policy documents or empty list"]
}}
"""


# --- Errors ---

class LLMError(Exception):
    def __init__(self, message: str, url: str = "", recoverable: bool = True):
        super().__init__(message)
        self.url = url
        self.recoverable = recoverable


class LLMAuthError(LLMError):
    def __init__(self, message: str):
        super().__init__(message, recoverable=False)


class LLMRateLimitError(LLMError):
    pass


class LLMParseError(LLMError):
    def __init__(self, message: str, raw_response: str = "", url: str = ""):
        super().__init__(message, url=url)
        self.raw_response = raw_response


class LLMServiceError(LLMError):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


# --- Helpers ---

_NULL_VALUES = (
    None, "null", "None", "N/A", "n/a", "", "unknown", "Unknown",
    "nicht verfügbar", "non disponible", "不明", "não disponível",
)


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, handling code blocks and raw JSON."""
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
    text = text.strip()
    if text.startswith("{"):
        depth = 0
        for i, char in enumerate(text):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[:i + 1]
    return text


def _coerce_types(data: dict) -> dict:
    """Coerce common type mismatches from LLM responses."""
    result = data.copy()

    # is_relevant → bool
    if "is_relevant" in result:
        val = result["is_relevant"]
        if isinstance(val, str):
            result["is_relevant"] = val.lower() in (
                "true", "yes", "1", "ja", "oui", "sí", "是", "да", "sim"
            )
        elif isinstance(val, (int, float)):
            result["is_relevant"] = bool(val)

    # relevance_score → int 0-10
    if "relevance_score" in result:
        val = result["relevance_score"]
        if isinstance(val, str):
            try:
                val = val.split("/")[0].split(" ")[0].strip()
                result["relevance_score"] = int(float(val))
            except (ValueError, IndexError):
                result["relevance_score"] = 0
        elif isinstance(val, float):
            result["relevance_score"] = int(val)
        if isinstance(result["relevance_score"], int):
            result["relevance_score"] = max(0, min(10, result["relevance_score"]))

    # Normalize null-like values
    # Optional[str] fields get None; required str fields get ""
    _OPTIONAL_FIELDS = {"effective_date", "bill_number"}
    for key in ["policy_name", "jurisdiction", "summary", "effective_date",
                "key_requirements", "bill_number", "relevance_explanation"]:
        if key in result and result[key] in _NULL_VALUES:
            if key == "relevance_explanation":
                result[key] = "No explanation provided"
            elif key in _OPTIONAL_FIELDS:
                result[key] = None
            else:
                result[key] = ""  # required str fields can't be None

    if "relevance_explanation" not in result or not result["relevance_explanation"]:
        result["relevance_explanation"] = "No explanation provided"

    # policy_type default
    if not result.get("policy_type") or result["policy_type"] in _NULL_VALUES:
        result["policy_type"] = "not_relevant" if not result.get("is_relevant") else "unknown"

    # Normalize list fields (referenced_policies, referenced_urls)
    for list_key in ("referenced_policies", "referenced_urls"):
        val = result.get(list_key)
        if val is None or val in _NULL_VALUES:
            result[list_key] = []
        elif isinstance(val, str):
            result[list_key] = [val] if val else []
        elif isinstance(val, list):
            result[list_key] = [item for item in val if item and item not in _NULL_VALUES]

    return result


# --- Client ---

class ClaudeClient:
    """Async Claude API client with two-stage analysis."""

    MAX_RETRIES = 3
    BASE_DELAY = 1.0
    MAX_DELAY = 30.0
    MAX_CONTENT_CHARS = 45000

    def __init__(
        self,
        api_key: str,
        analysis_model: str = "claude-sonnet-4-20250514",
        screening_model: str = "claude-haiku-4-5-20251001",
    ):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.analysis_model = analysis_model
        self.screening_model = screening_model
        self.cost = CostInfo()

    async def screen_relevance(
        self, content: str, url: str, min_confidence: int = 5,
    ) -> ScreeningResult:
        """Quick relevance screening using Haiku (fail-open on errors)."""
        screening_content = content[:5000]
        prompt = SCREENING_PROMPT.format(url=url, content=screening_content)

        try:
            import time
            _t0 = time.monotonic()
            response = await self.client.messages.create(
                model=self.screening_model,
                max_tokens=50,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            _latency_ms = int((time.monotonic() - _t0) * 1000)
            self.cost.screening_calls += 1
            if hasattr(response, "usage"):
                self.cost.input_tokens += response.usage.input_tokens
                self.cost.output_tokens += response.usage.output_tokens
                logger.info(
                    "llm_call: screening model=%s url=%s "
                    "input_tokens=%d output_tokens=%d latency_ms=%d",
                    self.screening_model, url,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                    _latency_ms,
                )

            raw = response.content[0].text
            try:
                data = json.loads(_extract_json(raw))
            except json.JSONDecodeError:
                logger.warning(f"Screening parse failed for {url}, assuming relevant")
                return ScreeningResult(relevant=True, confidence=5)

            relevant = data.get("relevant", True)
            if isinstance(relevant, str):
                relevant = relevant.lower() in ("true", "yes", "1")
            confidence = data.get("confidence", 5)
            if isinstance(confidence, str):
                try:
                    confidence = int(confidence)
                except ValueError:
                    confidence = 5
            confidence = max(1, min(10, confidence))

            return ScreeningResult(relevant=relevant, confidence=confidence)

        except anthropic.AuthenticationError as e:
            raise LLMAuthError(f"Authentication failed: {e}") from e
        except anthropic.NotFoundError:
            # Model doesn't exist — log ONCE and disable screening
            if not getattr(self, "_screening_model_warned", False):
                logger.error(
                    f"Screening model '{self.screening_model}' not found (404). "
                    f"All pages will bypass screening and go directly to analysis. "
                    f"Fix: update 'screening_model' in config/settings.yaml to a valid model."
                )
                self._screening_model_warned = True
            return ScreeningResult(relevant=True, confidence=5)
        except Exception as e:
            # Fail open: any error → assume relevant
            logger.warning(f"Screening error for {url}: {e}, assuming relevant")
            return ScreeningResult(relevant=True, confidence=5)

    async def analyze_policy(
        self, content: str, url: str, language: Optional[str] = None,
    ) -> PolicyAnalysis:
        """Full policy analysis with Sonnet. Retries on transient errors."""
        if len(content) > self.MAX_CONTENT_CHARS:
            content = content[:self.MAX_CONTENT_CHARS]

        last_error = None
        delay = self.BASE_DELAY

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return await self._call_analysis(content, url, language)

            except anthropic.AuthenticationError as e:
                raise LLMAuthError(f"Authentication failed: {e}") from e

            except anthropic.RateLimitError as e:
                if attempt < self.MAX_RETRIES:
                    retry_after = delay
                    try:
                        if hasattr(e, "response") and e.response:
                            retry_after = float(e.response.headers.get("retry-after", delay))
                    except (ValueError, AttributeError):
                        pass
                    logger.warning(f"Rate limited for {url}, waiting {retry_after:.1f}s")
                    await asyncio.sleep(retry_after)
                    delay = min(delay * 2, self.MAX_DELAY)
                else:
                    raise LLMRateLimitError(f"Rate limit after {self.MAX_RETRIES} retries") from e

            except anthropic.BadRequestError as e:
                error_msg = str(e).lower()
                if any(w in error_msg for w in ("context", "token", "length")):
                    if len(content) > 10000:
                        content = content[:10000]
                        logger.warning(f"Context too long for {url}, retrying truncated")
                        continue
                raise LLMError(f"Bad request: {e}", url=url) from e

            except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
                if attempt < self.MAX_RETRIES:
                    logger.warning(f"Connection error for {url}, retrying in {delay:.1f}s")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, self.MAX_DELAY)
                    last_error = e
                else:
                    raise LLMServiceError(f"Connection failed after retries: {e}") from e

            except (anthropic.InternalServerError, anthropic.APIStatusError) as e:
                if attempt < self.MAX_RETRIES:
                    logger.warning(f"Service error for {url}, retrying in {delay:.1f}s")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, self.MAX_DELAY)
                    last_error = e
                else:
                    raise LLMServiceError(f"Service error after retries: {e}") from e

            except LLMParseError:
                raise

        if last_error:
            raise LLMServiceError(f"Failed after {self.MAX_RETRIES} retries") from last_error
        raise LLMError("Failed for unknown reason", url=url)

    async def _call_analysis(
        self, content: str, url: str, language: Optional[str],
    ) -> PolicyAnalysis:
        """Make the actual analysis API call."""
        import time

        prompt = ANALYSIS_PROMPT.format(
            url=url, language=language or "Unknown", content=content,
        )
        _t0 = time.monotonic()
        response = await self.client.messages.create(
            model=self.analysis_model,
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        _latency_ms = int((time.monotonic() - _t0) * 1000)
        self.cost.analysis_calls += 1
        if hasattr(response, "usage"):
            self.cost.input_tokens += response.usage.input_tokens
            self.cost.output_tokens += response.usage.output_tokens
            logger.info(
                "llm_call: analysis model=%s url=%s "
                "input_tokens=%d output_tokens=%d latency_ms=%d",
                self.analysis_model, url,
                response.usage.input_tokens,
                response.usage.output_tokens,
                _latency_ms,
            )

        raw = response.content[0].text
        try:
            data = json.loads(_extract_json(raw))
        except json.JSONDecodeError as e:
            raise LLMParseError(f"Invalid JSON: {e}", raw_response=raw[:1000], url=url)

        data = _coerce_types(data)

        try:
            return PolicyAnalysis(**{
                k: v for k, v in data.items()
                if k in PolicyAnalysis.model_fields
            })
        except ValidationError as e:
            raise LLMParseError(f"Validation failed: {e}", raw_response=str(data)[:1000], url=url)

    def to_policy(
        self, analysis: PolicyAnalysis, url: str, language: str,
        domain_id: str = "", scan_id: str = "",
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
            key_requirements=analysis.key_requirements,
            domain_id=domain_id,
            scan_id=scan_id,
            referenced_policies=analysis.referenced_policies,
            referenced_urls=analysis.referenced_urls,
        )

    def update_cost_estimate(self):
        """Update USD cost estimate based on token usage."""
        # Pricing per million tokens (approximate)
        HAIKU_INPUT = 0.25
        HAIKU_OUTPUT = 1.25
        SONNET_INPUT = 3.0
        SONNET_OUTPUT = 15.0

        # Rough split: screening uses Haiku, analysis uses Sonnet
        # We don't track per-model tokens separately, so estimate
        if self.cost.screening_calls > 0 and self.cost.analysis_calls > 0:
            total_calls = self.cost.screening_calls + self.cost.analysis_calls
            haiku_frac = self.cost.screening_calls / total_calls
            sonnet_frac = self.cost.analysis_calls / total_calls

            input_cost = self.cost.input_tokens * (
                haiku_frac * HAIKU_INPUT + sonnet_frac * SONNET_INPUT
            ) / 1_000_000
            output_cost = self.cost.output_tokens * (
                haiku_frac * HAIKU_OUTPUT + sonnet_frac * SONNET_OUTPUT
            ) / 1_000_000
        else:
            input_cost = self.cost.input_tokens * SONNET_INPUT / 1_000_000
            output_cost = self.cost.output_tokens * SONNET_OUTPUT / 1_000_000

        self.cost.total_usd = round(input_cost + output_cost, 4)

    async def close(self):
        await self.client.close()
