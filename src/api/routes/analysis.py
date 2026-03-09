"""Single URL analysis endpoint — full pipeline on one URL."""

import os

from fastapi import APIRouter, Depends

from ..deps import get_config
from ...core.config import ConfigLoader
from ...core.crawler import AsyncCrawler
from ...core.extractor import HtmlExtractor
from ...core.keywords import KeywordMatcher
from ...core.llm import ClaudeClient, LLMError
from ...core.models import AnalyzeRequest
from ...core.verifier import Verifier

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/analyze")
async def analyze_url(
    request: AnalyzeRequest,
    config: ConfigLoader = Depends(get_config),
):
    """Analyze a single URL through the full pipeline."""
    url = request.url
    settings = config.settings

    # 1. Fetch
    crawler = AsyncCrawler(
        max_depth=0,
        max_pages=1,
        delay_seconds=0.5,
        timeout_seconds=settings.crawl.timeout_seconds,
        user_agent=settings.crawl.user_agent,
    )

    try:
        results = await crawler.crawl_domain(
            base_url=url,
            start_paths=[""],
            domain_id="single_analysis",
        )
    finally:
        await crawler.close()

    if not results or not results[0].is_success:
        status = results[0].status.value if results else "fetch_failed"
        error = results[0].error_message if results else "No response"
        return {
            "url": url,
            "crawl_status": status,
            "error": error,
        }

    result = results[0]

    # 2. Extract
    extractor = HtmlExtractor(settings.config_dir)
    extracted = extractor.extract(result.content, url)

    # 3. Keywords
    keyword_matcher = KeywordMatcher(config.keywords_config)
    kw_result = keyword_matcher.match(extracted.text)
    kw_relevant = keyword_matcher.is_relevant(kw_result, url=url)

    response = {
        "url": url,
        "title": extracted.title,
        "language": extracted.language,
        "word_count": extracted.word_count,
        "crawl_status": result.status.value,
        "keyword_score": kw_result.score + kw_result.url_bonus,
        "keyword_matches": [m.model_dump() for m in kw_result.matches],
        "categories_matched": kw_result.categories_matched,
        "passes_keyword_threshold": kw_relevant,
    }

    # 4. LLM analysis (if API key available)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key and kw_relevant:
        llm = ClaudeClient(
            api_key=api_key,
            analysis_model=settings.analysis.analysis_model,
            screening_model=settings.analysis.screening_model,
        )
        try:
            screening = await llm.screen_relevance(extracted.text, url)
            response["screening"] = {
                "relevant": screening.relevant,
                "confidence": screening.confidence,
            }

            if screening.relevant:
                analysis = await llm.analyze_policy(
                    extracted.text, url, extracted.language,
                )
                policy = llm.to_policy(
                    analysis, url,
                    language=extracted.language or "en",
                )

                if policy:
                    # Verify
                    verifier = Verifier()
                    flags = verifier.verify(policy)
                    policy.verification_flags = flags

                    response["policy"] = policy.model_dump(mode="json")
                    response["verification_flags"] = [f.value for f in flags]
                else:
                    response["policy"] = None

                response["analysis"] = {
                    "is_relevant": analysis.is_relevant,
                    "relevance_score": analysis.relevance_score,
                    "policy_type": analysis.policy_type,
                }
        except LLMError as e:
            response["llm_error"] = str(e)
        finally:
            await llm.close()
    elif not api_key:
        response["llm_note"] = "No ANTHROPIC_API_KEY set — LLM analysis skipped"

    return response


@router.get("/config/keywords")
def get_keywords_config(config: ConfigLoader = Depends(get_config)):
    """Get keywords configuration."""
    return config.keywords_config


@router.get("/config/settings")
def get_settings(config: ConfigLoader = Depends(get_config)):
    """Get application settings."""
    return config.settings.model_dump()
