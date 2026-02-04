"""Crawl data models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class PageStatus(Enum):
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


@dataclass
class CrawlResult:
    url: str
    status: PageStatus
    fetched_at: datetime = field(default_factory=datetime.utcnow)
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


@dataclass
class ExtractedContent:
    text: str
    title: Optional[str] = None
    language: Optional[str] = None
    word_count: int = 0
