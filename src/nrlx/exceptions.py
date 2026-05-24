"""Custom exception hierarchy for nrlx."""

class NRLXError(Exception):
    """Base exception for all nrlx-specific errors."""


class NRLXConfigError(NRLXError):
    """Raised when nrlx configuration is invalid or unavailable."""


class NRLXCacheError(NRLXError):
    """Raised when the local NRL cache cannot be created or accessed."""


class NRLXResponseError(NRLXError):
    """Raised when a response file cannot be built, parsed, or validated."""