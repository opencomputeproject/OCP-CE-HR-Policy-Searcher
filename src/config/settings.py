"""Application settings using Pydantic."""

from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class CrawlSettings(BaseModel):
    """Crawler configuration."""
    max_depth: int = Field(default=3, ge=1, le=10)
    max_pages_per_domain: int = Field(default=200, ge=1)
    delay_seconds: float = Field(default=3.0, ge=0.5)
    timeout_seconds: int = Field(default=30, ge=5)
    max_concurrent: int = Field(default=3, ge=1, le=10)
    user_agent: str = "OCP-PolicySearcher/1.0"
    respect_robots_txt: bool = True
    max_retries: int = 3
    force_playwright: bool = False


class AnalysisSettings(BaseModel):
    """Analysis configuration."""
    min_keyword_score: float = Field(default=3.0, ge=0)
    min_relevance_score: int = Field(default=5, ge=1, le=10)
    min_keyword_matches: int = Field(default=2, ge=1)
    enable_llm_analysis: bool = True
    llm_model: str = "claude-sonnet-4-20250514"
    max_content_length: int = Field(default=50000)
    llm_temperature: float = Field(default=0.0, ge=0, le=1)

    # Two-stage analysis settings (Phase 4)
    enable_two_stage: bool = True
    screening_model: str = "claude-haiku-4-20250514"
    screening_min_confidence: int = Field(default=5, ge=1, le=10)


class OutputSettings(BaseModel):
    """Output configuration."""
    spreadsheet_id: Optional[str] = None
    staging_sheet_name: str = "Staging"
    save_snapshots: bool = True
    snapshot_dir: str = "snapshots"


class LogSettings(BaseModel):
    """Logging configuration."""
    level: str = "INFO"
    log_dir: str = "logs"
    json_logs: bool = True
    human_logs: bool = True


class Settings(BaseSettings):
    """Main application settings."""
    crawl: CrawlSettings = Field(default_factory=CrawlSettings)
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    logging: LogSettings = Field(default_factory=LogSettings)

    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    google_credentials: Optional[str] = Field(default=None, alias="GOOGLE_CREDENTIALS")
    spreadsheet_id: Optional[str] = Field(default=None, alias="SPREADSHEET_ID")

    class Config:
        env_file = ".env"
        env_prefix = "POLICYSEARCH__"
        env_nested_delimiter = "__"
        extra = "ignore"  # Ignore extra fields like notifications
