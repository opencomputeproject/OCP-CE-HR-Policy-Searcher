"""Policy data models."""

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional


class PolicyType(Enum):
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


@dataclass
class Policy:
    url: str
    policy_name: str
    jurisdiction: str
    policy_type: PolicyType
    summary: str
    relevance_score: int

    effective_date: Optional[date] = None
    source_language: str = "English"
    bill_number: Optional[str] = None
    key_requirements: Optional[str] = None
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    crawl_status: str = "success"
    error_details: Optional[str] = None
    review_status: str = "new"

    def to_sheet_row(self) -> list:
        return [
            self.url,
            self.policy_name,
            self.jurisdiction,
            self.policy_type.value,
            self.summary,
            self.relevance_score,
            self.source_language,
            self.effective_date.isoformat() if self.effective_date else "",
            self.bill_number or "",
            self.key_requirements or "",
            self.discovered_at.isoformat(),
            self.crawl_status,
            self.error_details or "",
            self.review_status,
        ]

    @staticmethod
    def sheet_headers() -> list:
        return [
            "URL", "Policy Name", "Jurisdiction", "Policy Type",
            "Summary", "Relevance Score", "Source Language",
            "Effective Date", "Bill Number", "Key Requirements",
            "Discovered At", "Crawl Status", "Error Details", "Review Status",
        ]
