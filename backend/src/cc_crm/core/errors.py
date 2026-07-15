class CcCrmError(Exception):
    """Base class for expected application errors."""


class EntityNotFoundError(CcCrmError):
    pass


class ConflictError(CcCrmError):
    pass


class BusinessRuleError(CcCrmError):
    pass


class AuthenticationError(CcCrmError):
    pass


class RateLimitExceededError(CcCrmError):
    pass


class AIProviderError(CcCrmError):
    """Raised when an external AI provider (e.g. Anthropic) is unreachable,
    unconfigured, or returns an unusable response."""
