# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Kundenfreigabe von Stundenzetteln per Link - OHNE Login (wie der ICS-Feed in calendar_feed.py).

Der Link-Token ist der einzige Zugangsschutz: 256 Bit Zufall, in der Datenbank nur als Hash,
begrenzt gueltig, nur einmal nutzbar, gilt nur für genau einen Stundenzettel. Der Kunde sieht nur
die nötigen Daten (Name, Zeitraum, Stunden), nie Lohn- oder Verrechnungsdaten und keine IDs.

Schutz vor Raten: Fehlversuche (unbekannter, abgelaufener oder verbrauchter Token) werden pro
Client-IP gezählt (gleiche Technik wie beim Login, core/rate_limit.py); über dem Limit antwortet
der Server mit 429, BEVOR der Token ueberhaupt nachgeschlagen wird.
- unbekannter Token: 404 (nicht von "gab es nie" unterscheidbar)
- abgelaufen, verbraucht oder ersetzt: 410 mit allgemeiner Meldung"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request, status

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.core.rate_limit import LoginRateLimiter, client_ip
from cc_crm.schemas.staffing import (
    PublicTimesheetApprove,
    PublicTimesheetRead,
    PublicTimesheetReject,
)
from cc_crm.services.staffing_timesheets import (
    StaffingTimesheetService,
    TimesheetLinkExpiredError,
    TimesheetLinkNotFoundError,
)

router = APIRouter(prefix="/public/timesheets")

# 10 Fehlversuche je IP in 10 Minuten (ein Kunde, der den Link nur falsch abgetippt hat, bleibt weit
# darunter; ein Angreifer kommt mit 256 Bit Zufall praktisch nie an einen Treffer).
FAILED_LOOKUP_MAX = 10
FAILED_LOOKUP_WINDOW = timedelta(minutes=10)
timesheet_link_rate_limiter = LoginRateLimiter(
    "timesheet_link_ip", max_attempts=FAILED_LOOKUP_MAX, window=FAILED_LOOKUP_WINDOW
)

# Token-Parameter begrenzen (echte Token sind 43 Zeichen): kein unnoetig langer Eingabewert.
TokenParam = Annotated[str, Path(min_length=8, max_length=200)]

_EXPIRED = (
    "Dieser Link ist abgelaufen oder wurde bereits verwendet. "
    "Bitte beim Dienstleister einen neuen Link anfordern."
)
_UNKNOWN = "Dieser Link ist ungültig."


def _ip(request: Request) -> str:
    return client_ip(
        request.headers.get("cf-connecting-ip"),
        request.headers.get("x-forwarded-for"),
        request.client.host if request.client else None,
    )


def _guard(request: Request) -> str:
    ip = _ip(request)
    if timesheet_link_rate_limiter.is_blocked(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zu viele ungültige Versuche. Bitte in ein paar Minuten erneut versuchen.",
        )
    return ip


def _fail(ip: str, error: Exception) -> HTTPException:
    timesheet_link_rate_limiter.record_failure(ip)
    if isinstance(error, TimesheetLinkExpiredError):
        return HTTPException(status_code=status.HTTP_410_GONE, detail=_EXPIRED)
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_UNKNOWN)


@router.get("/{token}", response_model=PublicTimesheetRead)
def view_timesheet(
    token: TokenParam, session: DatabaseSession, request: Request
) -> PublicTimesheetRead:
    ip = _guard(request)
    try:
        return StaffingTimesheetService(session).public_view(token)
    except (TimesheetLinkNotFoundError, TimesheetLinkExpiredError) as error:
        raise _fail(ip, error) from error


@router.post("/{token}/approve", response_model=PublicTimesheetRead)
def approve_timesheet(
    token: TokenParam, payload: PublicTimesheetApprove, session: DatabaseSession, request: Request
) -> PublicTimesheetRead:
    ip = _guard(request)
    try:
        return StaffingTimesheetService(session).decide(
            token, approve=True, approver_name=payload.approver_name
        )
    except (TimesheetLinkNotFoundError, TimesheetLinkExpiredError) as error:
        raise _fail(ip, error) from error


@router.post("/{token}/reject", response_model=PublicTimesheetRead)
def reject_timesheet(
    token: TokenParam, payload: PublicTimesheetReject, session: DatabaseSession, request: Request
) -> PublicTimesheetRead:
    ip = _guard(request)
    try:
        return StaffingTimesheetService(session).decide(
            token, approve=False, approver_name=payload.approver_name, reason=payload.reason
        )
    except (TimesheetLinkNotFoundError, TimesheetLinkExpiredError) as error:
        raise _fail(ip, error) from error
