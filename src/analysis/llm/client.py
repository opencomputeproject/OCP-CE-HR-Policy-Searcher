"""Claude API client."""

import json
from typing import Optional
from datetime import date

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from pydantic import BaseModel

from ...models.policy import Policy, PolicyType
from .prompts import POLICY_ANALYSIS_PROMPT


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


class ClaudeClient:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
        # Track usage stats
        self.call_count = 0
        self.tokens_input = 0
        self.tokens_output = 0

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def analyze_policy(
        self,
        content: str,
        url: str,
        language: Optional[str] = None,
    ) -> PolicyAnalysis:
        prompt = POLICY_ANALYSIS_PROMPT.format(
            url=url,
            language=language or "Unknown",
            content=content[:50000],
        )

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )

        # Track usage
        self.call_count += 1
        if hasattr(response, 'usage'):
            self.tokens_input += response.usage.input_tokens
            self.tokens_output += response.usage.output_tokens

        text = response.content[0].text

        # Handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        data = json.loads(text.strip())
        return PolicyAnalysis(**data)

    def to_policy(
        self,
        analysis: PolicyAnalysis,
        url: str,
        language: str,
    ) -> Optional[Policy]:
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

    async def close(self) -> None:
        await self.client.close()
