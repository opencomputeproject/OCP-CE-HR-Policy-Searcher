"""LLM prompt templates."""

# =============================================================================
# SCREENING PROMPT (Haiku - fast, cheap)
# =============================================================================
# Used for quick relevance check before full analysis.
# Designed to be minimal for speed and cost.

SCREENING_PROMPT = """Quick relevance check. Does this page describe government POLICY about:
- Data center waste heat reuse/recovery
- Data center energy efficiency requirements
- District heating involving data centers
- Heat recovery mandates or incentives for data centers

URL: {url}

CONTENT (first 5000 chars):
{content}

RESPOND WITH JSON ONLY (no explanation):
{{"relevant": true/false, "confidence": 1-10}}
"""


# =============================================================================
# FULL ANALYSIS PROMPT (Sonnet - accurate, detailed)
# =============================================================================

POLICY_ANALYSIS_PROMPT = """
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

2. If relevant, extract:
   - Policy name/title
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
    "bill_number": "Number or null"
}}
"""
