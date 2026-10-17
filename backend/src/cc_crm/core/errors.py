class CcCrmError(Exception):
    """Base class for expected application errors."""


class EntityNotFoundError(CcCrmError):
    pass


class ConflictError(CcCrmError):
    pass


class OverlapConflictError(ConflictError):
    """NOMICON: Überlassung - ein anderer Einsatz desselben Leiharbeitnehmers liegt im selben
    Zeitraum (HTTP 409). `overlaps` ist die Liste der überschneidenden Einsätze für die Antwort."""

    def __init__(self, message: str, overlaps: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.overlaps = overlaps


class BusinessRuleError(CcCrmError):
    pass


class AuthenticationError(CcCrmError):
    pass


class PermissionDeniedError(CcCrmError):
    """Raised when an authenticated user is recognized but not allowed to
    perform the requested action (HTTP 403) - distinct from
    AuthenticationError (401, no/invalid credentials at all)."""


class RateLimitExceededError(CcCrmError):
    pass


class ConsentNotGrantedError(CcCrmError):
    """Kandidat hat keine Einwilligung zur Weitergabe erteilt
    (candidate.consent_received == False) - harter serverseitiger Block vor
    jedem Mail-Versand mit Kandidatenbezug (Punkt 1 des Auftrags "5 Hoch-
    Punkte umsetzen"). HTTP 403, kein Soft-Warning."""


class AIProviderError(CcCrmError):
    """Raised when an external AI provider (e.g. Anthropic) is unreachable,
    unconfigured, or returns an unusable response."""
