"""Custom exceptions."""

class PolicySearcherError(Exception):
    """Base exception."""
    pass

class ConfigurationError(PolicySearcherError):
    """Configuration error."""
    pass

class CrawlError(PolicySearcherError):
    """Crawl error."""
    pass

class AnalysisError(PolicySearcherError):
    """Analysis error."""
    pass

class OutputError(PolicySearcherError):
    """Output error."""
    pass
