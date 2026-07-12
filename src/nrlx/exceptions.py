"""Custom exception hierarchy for nrlx.

Every error nrlx raises is an ``NrlxError``, so callers can catch the whole
family with a single ``except NrlxError``. The subclasses distinguish which
subsystem failed.


"""


class NrlxError(Exception):
    """Base exception for all nrlx-specific errors."""


class NrlxCacheError(NrlxError):
    """Raised when the local NRL cache cannot be created or accessed."""


class NrlxResponseError(NrlxError):
    """Raised when a response file cannot be built, parsed, or validated."""


class NrlxNetworkError(NrlxError):
    """Raised when nrlx cannot communicate with the remote NRL service."""
