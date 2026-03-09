"""Tool definitions and dispatch for the standalone agent loop.

Defines 13 tools in Anthropic API format:
- 11 policy hub tools (same as MCP server)
- 1 built-in web_search (server-side, no dispatch needed)
- 1 add_domain tool (creates new domain YAML configs)
"""

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..core.config import ConfigLoader, ConfigurationError
from ..core.crawler import AsyncCrawler
from ..core.extractor import HtmlExtractor
from ..core.keywords import KeywordMatcher
from ..core.llm import ClaudeClient, LLMError
from ..core.verifier import Verifier
from ..orchestration.scan_manager import ScanManager
from .domain_generator import (
    generate_domain_id,
    detect_region,
    suggest_output_file,
    build_domain_entry,
    format_domain_yaml,
)

# ---------------------------------------------------------------------------
# Tool definitions — Anthropic API format
# ---------------------------------------------------------------------------

# The 11 existing tools (same schemas as MCP server, just different key name)
POLICY_TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_domains",
        "description": (
            "List government websites in the database. Filter by group "
            "(e.g. 'eu', 'nordic', 'us'), category, tags, or region. "
            "Use group='all' to see everything."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group": {"type": "string", "description": "Domain group: 'quick', 'eu', 'nordic', 'dach', 'north_america', 'asia_pacific', 'all'"},
                "category": {"type": "string", "description": "Filter by category (e.g. 'energy_ministry')"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by tags"},
                "region": {"type": "string", "description": "Filter by region (e.g. 'eu', 'us', 'apac')"},
            },
        },
    },
    {
        "name": "get_domain_config",
        "description": "Get full configuration for a specific government website by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain_id": {"type": "string", "description": "Domain ID (e.g. 'bmwk_de', 'uk_legislation')"},
            },
            "required": ["domain_id"],
        },
    },
    {
        "name": "start_scan",
        "description": (
            "Start scanning government websites to discover policies. "
            "Runs in the background — use get_scan_status to check progress. "
            "Returns a scan_id immediately."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "domains": {"type": "string", "default": "quick", "description": "Which domains to scan: 'quick', 'eu', 'nordic', 'dach', 'north_america', 'asia_pacific', 'all'"},
                "max_concurrent": {"type": "integer", "default": 5, "description": "Max parallel workers (1-20)"},
                "skip_llm": {"type": "boolean", "default": False, "description": "Skip AI analysis (keyword-only mode)"},
            },
        },
    },
    {
        "name": "get_scan_status",
        "description": "Check the progress of a running or completed scan. Shows per-domain status, policies found, and costs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scan_id": {"type": "string", "description": "Scan ID from start_scan"},
            },
            "required": ["scan_id"],
        },
    },
    {
        "name": "stop_scan",
        "description": "Cancel a running scan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scan_id": {"type": "string", "description": "Scan ID to cancel"},
            },
            "required": ["scan_id"],
        },
    },
    {
        "name": "analyze_url",
        "description": (
            "Analyze a single webpage for policy content. Fetches the page, "
            "extracts text, checks for policy keywords, and uses AI to identify "
            "and classify any policies found."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to analyze (e.g. 'https://example.gov/policy')"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "match_keywords",
        "description": "Test keyword scoring on arbitrary text. Shows which policy-related keywords are found and the relevance score.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to check for policy keywords"},
                "language": {"type": "string", "default": "en", "description": "Language code (en, de, fr, etc.)"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "search_policies",
        "description": "Search through discovered policies. Filter by country, policy type, relevance score, or keywords.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keywords"},
                "jurisdiction": {"type": "string", "description": "Country or jurisdiction (e.g. 'Germany', 'Denmark')"},
                "policy_type": {"type": "string", "description": "Type: 'law', 'regulation', 'directive', 'incentive', 'grant', 'plan', 'standard'"},
                "min_score": {"type": "integer", "description": "Minimum relevance score (1-10)"},
            },
        },
    },
    {
        "name": "get_policy_stats",
        "description": "Get an overview of all discovered policies — totals by country, type, and flagged items.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_audit_advisory",
        "description": "Get AI-generated insights and recommendations from a completed scan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scan_id": {"type": "string", "description": "Scan ID"},
            },
            "required": ["scan_id"],
        },
    },
    {
        "name": "estimate_cost",
        "description": "Estimate the API cost before running a scan. Shows expected number of pages, AI calls, and dollar cost.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domains": {"type": "string", "description": "Domain group to estimate (e.g. 'eu', 'quick', 'all')"},
            },
            "required": ["domains"],
        },
    },
]

# add_domain tool
ADD_DOMAIN_TOOL: dict[str, Any] = {
    "name": "add_domain",
    "description": (
        "Add a new government website to the database. Fetches the URL to "
        "auto-detect the site name, language, and region. Creates a YAML "
        "config file so the site can be scanned in future runs."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL of the government website to add"},
            "name": {"type": "string", "description": "Optional: override the auto-detected site name"},
        },
        "required": ["url"],
    },
}

# Anthropic's built-in web search tool (server-side, no dispatch needed)
WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20250305",
    "name": "web_search",
}


def get_all_tools() -> list[dict[str, Any]]:
    """Return all 13 tools for messages.create(tools=...)."""
    return POLICY_TOOLS + [ADD_DOMAIN_TOOL, WEB_SEARCH_TOOL]


# ---------------------------------------------------------------------------
# Tool dispatch — executes tools locally
# ---------------------------------------------------------------------------

async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    config: ConfigLoader,
    scan_manager: ScanManager,
) -> dict[str, Any]:
    """Execute a tool and return the result as a dict.

    This mirrors the dispatch logic in src/mcp/server.py but returns
    plain dicts instead of TextContent.

    The web_search tool is server-side and never reaches this function.
    """
    try:
        if name == "list_domains":
            group = arguments.get("group", "all")
            domains = config.get_enabled_domains(group)
            category = arguments.get("category")
            tags = arguments.get("tags")
            region = arguments.get("region")

            if category:
                domains = [d for d in domains if d.get("category") == category]
            if tags:
                domains = [d for d in domains if any(t in d.get("tags", []) for t in tags)]
            if region:
                domains = [d for d in domains if region in d.get("region", [])]

            return {
                "domains": [
                    {"id": d["id"], "name": d["name"], "base_url": d["base_url"],
                     "region": d.get("region", []), "category": d.get("category")}
                    for d in domains
                ],
                "count": len(domains),
            }

        elif name == "get_domain_config":
            domain_id = arguments["domain_id"]
            all_domains = {d["id"]: d for d in config.domains_config.get("domains", [])}
            if domain_id not in all_domains:
                return {"error": f"Domain '{domain_id}' not found"}
            return all_domains[domain_id]

        elif name == "start_scan":
            job = await scan_manager.start_scan(
                domains_group=arguments.get("domains", "quick"),
                max_concurrent=arguments.get("max_concurrent", 5),
                skip_llm=arguments.get("skip_llm", False),
            )
            return {
                "scan_id": job.scan_id,
                "status": job.status.value,
                "domain_count": job.domain_count,
            }

        elif name == "get_scan_status":
            scan_id = arguments["scan_id"]
            job = scan_manager.jobs.get(scan_id)
            if not job:
                return {"error": f"Scan '{scan_id}' not found"}
            policies = scan_manager.get_policies(scan_id)
            return {
                "scan_id": job.scan_id,
                "status": job.status.value,
                "domain_count": job.domain_count,
                "policy_count": job.policy_count,
                "progress": {
                    "total": job.progress.total_domains,
                    "completed": job.progress.completed_domains,
                    "domains": [dp.model_dump() for dp in job.progress.domains],
                },
                "cost": job.cost.model_dump() if job.cost else None,
                "policies": [p.model_dump(mode="json") for p in policies[:20]],
            }

        elif name == "stop_scan":
            success = await scan_manager.stop_scan(arguments["scan_id"])
            return {"cancelled": success}

        elif name == "analyze_url":
            url = arguments["url"]
            settings = config.settings

            crawler = AsyncCrawler(
                max_depth=0, max_pages=1,
                delay_seconds=0.5,
                timeout_seconds=settings.crawl.timeout_seconds,
                user_agent=settings.crawl.user_agent,
            )
            try:
                results = await crawler.crawl_domain(url, [""], "agent_analysis")
            finally:
                await crawler.close()

            if not results or not results[0].is_success:
                return {
                    "url": url,
                    "status": results[0].status.value if results else "failed",
                    "error": results[0].error_message if results else "No response",
                }

            extractor = HtmlExtractor(settings.config_dir)
            extracted = extractor.extract(results[0].content, url)

            kw_matcher = KeywordMatcher(config.keywords_config)
            kw_result = kw_matcher.match(extracted.text)

            response: dict[str, Any] = {
                "url": url,
                "title": extracted.title,
                "language": extracted.language,
                "word_count": extracted.word_count,
                "keyword_score": kw_result.score + kw_result.url_bonus,
                "categories": kw_result.categories_matched,
                "matches": len(kw_result.matches),
            }

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if api_key and kw_matcher.is_relevant(kw_result, url=url):
                llm = ClaudeClient(api_key=api_key)
                try:
                    screening = await llm.screen_relevance(extracted.text, url)
                    response["screening"] = {"relevant": screening.relevant, "confidence": screening.confidence}

                    if screening.relevant:
                        analysis = await llm.analyze_policy(extracted.text, url, extracted.language)
                        policy = llm.to_policy(analysis, url, extracted.language or "en")
                        if policy:
                            verifier = Verifier()
                            flags = verifier.verify(policy)
                            response["policy"] = policy.model_dump(mode="json")
                            response["flags"] = [f.value for f in flags]
                except LLMError as e:
                    response["llm_error"] = str(e)
                finally:
                    await llm.close()

            return response

        elif name == "match_keywords":
            kw_matcher = KeywordMatcher(config.keywords_config)
            result = kw_matcher.match(arguments["text"])
            return {
                "score": result.score,
                "matches": [m.model_dump() for m in result.matches],
                "categories": result.categories_matched,
                "is_excluded": result.is_excluded,
            }

        elif name == "search_policies":
            policies = scan_manager.get_all_policies()
            jurisdiction = arguments.get("jurisdiction")
            policy_type = arguments.get("policy_type")
            min_score = arguments.get("min_score")
            query = arguments.get("query", "").lower()

            filtered = []
            for p in policies:
                if jurisdiction and jurisdiction.lower() not in (p.jurisdiction or "").lower():
                    continue
                if policy_type and p.policy_type.value != policy_type:
                    continue
                if min_score and p.relevance_score < min_score:
                    continue
                if query and query not in (p.policy_name + " " + p.summary).lower():
                    continue
                filtered.append(p)

            return {
                "policies": [p.model_dump(mode="json") for p in filtered],
                "count": len(filtered),
            }

        elif name == "get_policy_stats":
            policies = scan_manager.get_all_policies()
            by_jurisdiction: dict[str, int] = {}
            by_type: dict[str, int] = {}
            for p in policies:
                j = p.jurisdiction or "Unknown"
                by_jurisdiction[j] = by_jurisdiction.get(j, 0) + 1
                by_type[p.policy_type.value] = by_type.get(p.policy_type.value, 0) + 1

            return {
                "total": len(policies),
                "by_jurisdiction": by_jurisdiction,
                "by_type": by_type,
                "flagged": sum(1 for p in policies if p.verification_flags),
            }

        elif name == "get_audit_advisory":
            scan_id = arguments["scan_id"]
            job = scan_manager.jobs.get(scan_id)
            if not job:
                return {"error": f"Scan '{scan_id}' not found"}
            return {
                "scan_id": scan_id,
                "advisory": job.audit_advisory or "No advisory available (scan may still be running)",
            }

        elif name == "estimate_cost":
            return scan_manager.estimate_cost(arguments["domains"])

        elif name == "add_domain":
            return await _execute_add_domain(arguments, config)

        else:
            return {"error": f"Unknown tool: {name}"}

    except ConfigurationError as e:
        return {"error": f"Configuration error: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}


async def _execute_add_domain(
    arguments: dict[str, Any],
    config: ConfigLoader,
) -> dict[str, Any]:
    """Add a new domain by fetching URL metadata and creating YAML config."""
    url = arguments["url"]
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if not hostname:
        return {"error": f"Invalid URL: {url}"}

    # Check if domain already exists
    domain_id = generate_domain_id(hostname)
    existing = {d["id"] for d in config.domains_config.get("domains", [])}
    if domain_id in existing:
        return {
            "already_exists": True,
            "domain_id": domain_id,
            "message": f"Domain '{domain_id}' already exists in the database.",
        }

    # Fetch URL to get metadata
    settings = config.settings
    crawler = AsyncCrawler(
        max_depth=0, max_pages=1,
        delay_seconds=0.5,
        timeout_seconds=settings.crawl.timeout_seconds,
        user_agent=settings.crawl.user_agent,
    )
    try:
        results = await crawler.crawl_domain(url, [""], "add_domain")
    finally:
        await crawler.close()

    # Extract metadata
    title = hostname
    language = "en"
    requires_playwright = False

    if results and results[0].is_success:
        extractor = HtmlExtractor(settings.config_dir)
        extracted = extractor.extract(results[0].content, url)
        if extracted.title:
            title = extracted.title
        if extracted.language:
            language = extracted.language
    elif results and results[0].status.value == "js_required":
        requires_playwright = True

    # Override name if provided
    name = arguments.get("name", title)

    # Build paths
    path = parsed.path or "/"
    query = parsed.query
    start_path = path
    if query:
        start_path = f"{path}?{query}"
    start_paths = [start_path] if start_path != "/" else ["/"]

    # Build entry
    base_url = f"{parsed.scheme}://{hostname}"
    region = detect_region(hostname)
    entry = build_domain_entry(
        name=name,
        domain_id=domain_id,
        base_url=base_url,
        start_paths=start_paths,
        language=language,
        requires_playwright=requires_playwright,
        region=region,
    )

    # Save to config directory
    output_file = suggest_output_file(hostname)
    config_dir = Path(config.config_dir) / "domains"
    output_path = config_dir / output_file

    # Create parent directories if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    yaml_content = format_domain_yaml(entry, standalone=True)

    if output_path.exists():
        # Append to existing file
        append_content = format_domain_yaml(entry, standalone=False)
        with open(output_path, "a", encoding="utf-8") as f:
            f.write("\n" + append_content)
    else:
        output_path.write_text(yaml_content, encoding="utf-8")

    # Reload config to pick up the new domain
    config.load()

    return {
        "success": True,
        "domain_id": domain_id,
        "name": name,
        "base_url": base_url,
        "region": region,
        "language": language,
        "config_file": str(output_path),
        "message": f"Added '{name}' ({domain_id}) to the database. It can now be scanned.",
    }
