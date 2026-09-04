"""Data models for the OCP CE HR Policy Searcher."""

from datetime import datetime, date
from enum import Enum
from typing import Optional, Any, Literal

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Model IDs - single source of truth for Claude model defaults.
#
# Users override via .env (SCREENING_MODEL, ANALYSIS_MODEL) or settings.yaml.
# All other modules import these constants instead of hardcoding model strings.
# Use undated aliases (e.g. "claude-sonnet-4-6") where available so that the
# API automatically resolves to the latest patch version.
# ---------------------------------------------------------------------------
DEFAULT_ANALYSIS_MODEL = "claude-sonnet-4-6"
DEFAULT_SCREENING_MODEL = "claude-haiku-4-5-20251001"

# Document kinds the cheap screener drops before any analysis call (WP-5) -
# see src/core/scanner.py's screening_decision and
# config/settings.yaml's analysis.screener_reject_kinds, which overrides
# this default via src/core/config.py.
# Hard drops: never a policy in the reviewer's 143 rows (WP-5).
DEFAULT_SCREENER_REJECT_KINDS = ["question", "speech"]
# Soft drops: dropped only when the screener found neither a data-centre
# sentence nor a heat-reuse sentence; with either, escalated to the strong
# model. Measured 2026-09-03 on her rows: two kept agency pages and one
# kept press release came back as "report"/"article" WITH quotes, so a
# hard drop on these kinds would have lost keeps (see ADR-0011).
DEFAULT_SCREENER_SOFT_REJECT_KINDS = ["report", "article"]


# --- Enums ---

class PolicyType(str, Enum):
    LAW = "law"
    REGULATION = "regulation"
    DIRECTIVE = "directive"
    INCENTIVE = "incentive"
    TAX_INCENTIVE = "tax_incentive"
    GRANT = "grant"
    PLAN = "plan"
    REQUIREMENT = "requirement"
    STANDARD = "standard"
    GUIDANCE = "guidance"
    MATCHING_PLATFORM = "matching_platform"
    UNKNOWN = "unknown"


class PageStatus(str, Enum):
    SUCCESS = "success"
    PAYWALL_DETECTED = "paywall"
    CAPTCHA_DETECTED = "captcha"
    LOGIN_REQUIRED = "login_required"
    ACCESS_DENIED = "access_denied"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    PARSE_ERROR = "parse_error"
    RATE_LIMITED = "rate_limited"
    JS_REQUIRED = "js_required"
    UNKNOWN_ERROR = "unknown_error"


class ScanStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DomainScanStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class VerificationFlag(str, Enum):
    JURISDICTION_MISMATCH = "jurisdiction_mismatch"
    FUTURE_DATE = "future_date"
    GENERIC_NAME = "generic_name"
    DUPLICATE_URL = "duplicate_url"
    LOW_CONFIDENCE_HIGH_SCORE = "low_confidence_high_score"


# --- Domain Configuration ---

class DomainConfig(BaseModel):
    id: str
    name: str
    base_url: str
    enabled: bool = True
    region: list[str] = Field(default_factory=list)
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    policy_types: list[str] = Field(default_factory=list)
    start_paths: list[str] = Field(default_factory=lambda: ["/"])
    max_depth: Optional[int] = None
    max_pages: Optional[int] = None
    requires_playwright: bool = False
    min_keyword_score: Optional[float] = None
    allowed_path_patterns: list[str] = Field(default_factory=list)
    blocked_path_patterns: list[str] = Field(default_factory=list)


# --- Crawl Results ---

class CrawlResult(BaseModel):
    url: str
    status: PageStatus
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    content: Optional[str] = None
    content_type: Optional[str] = None
    title: Optional[str] = None
    language: Optional[str] = None
    response_time_ms: Optional[int] = None
    content_length: Optional[int] = None
    error_message: Optional[str] = None
    requires_human_review: bool = False
    used_playwright: bool = False
    domain_id: Optional[str] = None
    # Set by structured sources that know the document's stage (bill
    # status, open consultation); overrides analysis inference.
    lifecycle_stage: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.status == PageStatus.SUCCESS

    @property
    def is_blocked(self) -> bool:
        return self.status in {
            PageStatus.PAYWALL_DETECTED,
            PageStatus.CAPTCHA_DETECTED,
            PageStatus.LOGIN_REQUIRED,
            PageStatus.ACCESS_DENIED,
        }


class ExtractedContent(BaseModel):
    text: str
    title: Optional[str] = None
    language: Optional[str] = None
    word_count: int = 0


# --- Keyword Results ---

class KeywordMatch(BaseModel):
    term: str
    category: str
    weight: float
    language: str


class KeywordResult(BaseModel):
    score: float
    matches: list[KeywordMatch] = Field(default_factory=list)
    categories_matched: list[str] = Field(default_factory=list)
    url_bonus: float = 0.0
    passes_threshold: bool = False
    is_near_miss: bool = False
    is_excluded: bool = False


# --- LLM Results ---

class ScreeningResult(BaseModel):
    relevant: bool
    confidence: int = 5
    error: Optional[str] = None
    # WP-5: the screener's three narrow questions replace one wide
    # relevance judgment. kind is one of the fixed list in SCREENING_PROMPT
    # (src/core/llm.py) - None means a parsing/API fallback produced this
    # result, never a real verdict; see screening_decision in
    # src/core/scanner.py, which always proceeds on kind=None. dc_quote and
    # heat_quote are the source-text sentences the model quoted, or None
    # when it found none; relevant is derived from them
    # (src.core.llm.parse_screening_response), never asked for directly.
    kind: Optional[str] = None
    dc_quote: Optional[str] = None
    heat_quote: Optional[str] = None
    # False means a quote is kept - never dropped for this alone - but did
    # not literally appear (whitespace normalised) in the excerpt the model
    # was shown, so it is worth a reviewer's second look.
    quote_verified: bool = True


class PolicyAnalysis(BaseModel):
    is_relevant: bool = False
    relevance_score: int = 0
    policy_type: str = "unknown"
    policy_name: str = ""
    # English translation of policy_name (WP-35). Optional/defaults to None
    # so older LLM responses and fixtures that predate this field still
    # parse without a validation error.
    policy_name_en: Optional[str] = None
    jurisdiction: str = ""
    summary: str = ""
    key_requirements: str = ""
    effective_date: Optional[str] = None
    source_language: str = "English"
    confidence: int = 5
    referenced_policies: list[str] = Field(default_factory=list)
    referenced_urls: list[str] = Field(default_factory=list)
    lifecycle_stage: str = "unknown"
    # Index/listing pages describe several policies; the primary one uses
    # the fields above, the rest arrive here.
    additional_policies: list["PolicyAnalysis"] = Field(default_factory=list)


# --- Policy (final output) ---

# Where a policy sits in its life: sources set this when they know it
# (bill status, consultation window); otherwise analysis infers it.
LIFECYCLE_STAGES = (
    "proposed", "consultation", "in_committee", "passed",
    "enacted", "transposition_notified", "amended", "unknown",
)


class Policy(BaseModel):
    url: str
    policy_name: str
    # English translation of policy_name (WP-35); None when not yet
    # translated (see src/output/backfill_english.py) or when policy_name
    # was already English.
    policy_name_en: Optional[str] = None
    jurisdiction: str
    policy_type: PolicyType
    summary: str
    relevance_score: int
    effective_date: Optional[date] = None
    source_language: str = "English"
    bill_number: Optional[str] = None
    key_requirements: Optional[str] = None
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    crawl_status: str = "success"
    error_details: Optional[str] = None
    review_status: str = "new"
    scan_id: Optional[str] = None
    domain_id: Optional[str] = None
    verification_flags: list[VerificationFlag] = Field(default_factory=list)
    referenced_policies: list[str] = Field(default_factory=list)
    referenced_urls: list[str] = Field(default_factory=list)
    lifecycle_stage: str = "unknown"
    # The screener's kind classification and its two quotes (WP-5), carried
    # from ScreeningResult onto every policy the page produced - so a
    # reviewer can see why the row exists without re-reading the source.
    # None for anything discovered before WP-5, or when screening was
    # skipped entirely (skip_llm, cache hit). Rides in the raw JSON; the
    # sheet is unchanged.
    evidence: Optional[dict] = None

    @staticmethod
    def sheet_headers() -> list[str]:
        """Staging headers, aligned with the Heat Reuse Policies Database tab."""
        from .policy_schema import STAGING_HEADERS
        return list(STAGING_HEADERS)



# --- Scan Events (WebSocket) ---

class ScanEvent(BaseModel):
    scan_id: str
    type: Literal[
        "scan_started",
        "domain_started",
        "page_fetched",
        "keyword_match",
        "policy_found",
        "domain_complete",
        "verification_complete",
        "audit_complete",
        "scan_complete",
        "error",
    ]
    domain_id: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# --- Scan Job ---

class DomainProgress(BaseModel):
    domain_id: str
    domain_name: str
    status: DomainScanStatus = DomainScanStatus.PENDING
    pages_crawled: int = 0
    pages_filtered: int = 0
    # Rejection breakdown: pages_filtered alone lumps every drop reason
    # into one opaque number, hiding recall loss.
    filtered_short_content: int = 0
    filtered_excluded: int = 0
    filtered_keywords: int = 0
    filtered_screening: int = 0
    # Dropped for never referencing a data centre. Counted separately
    # from the keyword and screening drops so the cost of the scope
    # rule is visible rather than folded into the total.
    filtered_out_of_scope: int = 0
    # Dropped by a source's document-type allow-list.
    filtered_doc_type: int = 0
    # Dropped by the pre-screen link check.
    filtered_link: int = 0
    # Folded into an existing kept row.
    filtered_duplicate: int = 0
    # Dropped by the screener's document-kind question.
    screened_kind: int = 0
    near_misses: int = 0
    keywords_matched: int = 0
    policies_found: int = 0
    llm_skipped: int = 0
    errors: int = 0
    error_message: Optional[str] = None


class ScanProgress(BaseModel):
    total_domains: int = 0
    completed_domains: int = 0
    running_domains: int = 0
    domains: list[DomainProgress] = Field(default_factory=list)


class CostInfo(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    screening_calls: int = 0
    analysis_calls: int = 0
    # Per-stage token counters (WP-22) - input_tokens/output_tokens above
    # remain the maintained totals (screening + analysis + auditor) so the
    # scans table and any other consumer of the aggregate keeps working;
    # these let update_cost_estimate() price each stage at its own model
    # instead of blending by call-count fraction over a shared pool.
    screening_input_tokens: int = 0
    screening_output_tokens: int = 0
    analysis_input_tokens: int = 0
    analysis_output_tokens: int = 0
    total_usd: float = 0.0


class SheetsExportStatus(BaseModel):
    """Tracks Google Sheets export state throughout a scan."""
    configured: bool = False           # Were credentials + spreadsheet_id provided?
    connected: bool = False            # Did initial connection succeed?
    exported_count: int = 0            # Policies successfully written to Sheets
    failed_count: int = 0              # Policies that failed to export
    error: Optional[str] = None        # Last error message (if any)
    status: str = "not_configured"     # not_configured | connected | failed | skipped


class ScanJob(BaseModel):
    scan_id: str
    status: ScanStatus = ScanStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    domain_group: str = ""
    domain_count: int = 0
    policy_count: int = 0
    progress: ScanProgress = Field(default_factory=ScanProgress)
    cost: CostInfo = Field(default_factory=CostInfo)
    audit_advisory: Optional[str] = None
    options: dict[str, Any] = Field(default_factory=dict)
    sheets_export: SheetsExportStatus = Field(default_factory=SheetsExportStatus)
    # Set once running cost reaches the scan's budget_usd cap (WP-22b);
    # the scan still completes normally with whatever domains finished.
    budget_reached: bool = False


# --- API Request/Response Schemas ---

# Channels a scan can be scoped to. "news" has its own runner (not
# scan_manager) and never appears as a domain's classified channel.
VALID_SCAN_CHANNELS = {"crawl", "law_apis", "transposition", "news"}


class ScanRequest(BaseModel):
    domains: str = "quick"
    max_concurrent: int = Field(default=5, ge=1, le=20)
    skip_llm: bool = False
    dry_run: bool = False
    deep: bool = False
    discover: bool = False
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    policy_type: Optional[str] = None
    channels: list[str] = Field(default_factory=lambda: ["crawl"])
    # Per-request overrides for structured sources (e.g. {"state": "CA",
    # "terms": [...]} from a place-first search). Crawl domains ignore this.
    source_params: Optional[dict] = None
    # Mid-scan budget stop (WP-22b). None = no cap unless the route applies
    # its default_scan_budget_usd (WP-6a/PL-004) - see no_budget below.
    # Schedules pass their remaining monthly ceiling here so a scan stops
    # launching further domains once running cost reaches it.
    budget_usd: Optional[float] = Field(default=None, ge=0)
    # Explicit opt-out (WP-6a) of the default_scan_budget_usd the route
    # applies when budget_usd is omitted. False (the default) means an
    # omitted budget_usd gets the configured default; True means this scan
    # really is meant to run uncapped.
    no_budget: bool = False

    @model_validator(mode="after")
    def validate_scan_mode(self) -> "ScanRequest":
        if self.deep and self.discover:
            raise ValueError("Choose one scan mode: standard, deep, or discover")
        return self

    @model_validator(mode="after")
    def validate_channels(self) -> "ScanRequest":
        invalid = sorted(set(self.channels) - VALID_SCAN_CHANNELS)
        if invalid:
            raise ValueError(
                f"Invalid channel(s): {invalid}. "
                f"Valid values: {sorted(VALID_SCAN_CHANNELS)}"
            )
        return self


class AnalyzeRequest(BaseModel):
    url: str


class CostEstimateRequest(BaseModel):
    domains: str


class CostEstimate(BaseModel):
    domain_count: int
    estimated_pages: int
    estimated_keyword_passes: int
    estimated_screening_calls: int
    estimated_analysis_calls: int
    estimated_cost_usd: float


class PolicyStats(BaseModel):
    total: int = 0
    by_jurisdiction: dict[str, int] = Field(default_factory=dict)
    by_type: dict[str, int] = Field(default_factory=dict)
    by_score_range: dict[str, int] = Field(default_factory=dict)
    flagged_count: int = 0


# --- Settings ---

class CrawlSettings(BaseModel):
    max_depth: int = Field(default=3, ge=1, le=10)
    max_pages_per_domain: int = Field(default=200, ge=1)
    delay_seconds: float = Field(default=3.0, ge=0.5)
    timeout_seconds: int = Field(default=30, ge=5)
    max_concurrent: int = Field(default=3, ge=1, le=10)
    user_agent: str = "OCP-PolicyHub/1.0"
    respect_robots_txt: bool = True
    max_retries: int = 3
    force_playwright: bool = False


class AnalysisSettings(BaseModel):
    min_keyword_score: float = Field(default=3.0, ge=0)
    min_relevance_score: int = Field(default=5, ge=1, le=10)
    min_keyword_matches: int = Field(default=2, ge=1)
    enable_llm_analysis: bool = True
    analysis_model: str = DEFAULT_ANALYSIS_MODEL
    screening_model: str = DEFAULT_SCREENING_MODEL
    max_content_length: int = Field(default=50000)
    enable_two_stage: bool = True
    screening_min_confidence: int = Field(default=5, ge=1, le=10)
    # Whether a document must reference a data centre to be in scope.
    # required | adjacent | off. See src/core/scope.py; the reviewer's
    # rule is required, and it is the default.
    data_center_required: str = "required"
    # Document kinds the cheap screener drops before any analysis call
    # (WP-5): a parliamentary question, transcript, report or article is
    # never a policy, whatever it quotes. See src/core/scanner.py's
    # screening_decision. Part of the analysis block, so changing it
    # changes the rules fingerprint (src/core/rules_version.py) like every
    # other screening rule.
    screener_reject_kinds: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SCREENER_REJECT_KINDS)
    )
    screener_soft_reject_kinds: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SCREENER_SOFT_REJECT_KINDS)
    )
    # Default running-cost cap (WP-6a/PL-004) applied to a scan that omits
    # budget_usd, so a scan the estimator badly mis-priced cannot run away
    # unnoticed. The full 402-source scan of 2026-09-01 cost $9.05; 25
    # leaves headroom while still stopping a runaway. 0 disables the
    # default (a scan then runs uncapped unless it passes its own
    # budget_usd, exactly as before this setting existed).
    default_scan_budget_usd: float = 25.0


class OutputSettings(BaseModel):
    spreadsheet_id: Optional[str] = None
    staging_sheet_name: str = "Staging"
    google_credentials_b64: Optional[str] = None
    # The reviewer's sheet of record (ADR-0005) - production's spreadsheet_id
    # points at a copy, so the review importer needs its own, independently
    # overridable id. None means "same sheet as spreadsheet_id"; ConfigLoader
    # resolves that fallback at load time (src/core/config.py).
    review_spreadsheet_id: Optional[str] = None
    # Whether src.orchestration.schedule_runner.fire_schedule runs the review
    # import before each monthly scan. Off by default: ADR-0005 is Proposed,
    # not Accepted, so this mechanism ships built but switched off (WP-2).
    import_reviews_before_scan: bool = False
    # The status a "keep" verdict in her column maps to. "promoted" keeps its
    # existing meaning - moved to the master tab by a person - and a keep
    # never downgrades an already-promoted row to this value.
    review_keep_status: Literal["reviewed", "promoted"] = "reviewed"


class AppSettings(BaseModel):
    crawl: CrawlSettings = Field(default_factory=CrawlSettings)
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    anthropic_api_key: Optional[str] = None
    config_dir: str = "config"
    data_dir: str = "data"
    max_concurrent_scans: int = 5
