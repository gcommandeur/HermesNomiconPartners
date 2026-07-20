from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.models.user import User
from cc_crm.repositories.calendar_events import CalendarEventRepository
from cc_crm.services.ics_feed import build_ics_feed

router = APIRouter(prefix="/calendar")


@router.get("/feed/{feed_token}.ics")
def calendar_feed(feed_token: str, session: DatabaseSession) -> Response:
    """Oeffentlicher ICS-Feed-Endpunkt (KEIN Bearer-Auth) - Outlook kann beim
    Abonnieren einer Internet-URL keine Header mitschicken, deshalb dient der
    schwer erratbare feed_token selbst als Zugangsschutz (wie ein Passwort in
    der URL). Bei fehlendem Treffer bewusst 404 statt 401/403, damit ein
    Angreifer nicht unterscheiden kann, ob "das Token-Muster grundsaetzlich
    existiert" - beides sieht identisch aus."""
    user = session.scalar(select(User).where(User.calendar_feed_token == feed_token))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Auch fuer Admins zeigt der eigene Feed nur die eigenen Termine (Nutzer-
    # Vorgabe: "Feed bleibt einfach: 1 Nutzer = 1 Feed = eigene Termine") -
    # fuer "alle Termine" nutzt der Admin die Web-Oberflaeche.
    events = CalendarEventRepository(session).for_owner(user.id)
    ics_bytes = build_ics_feed(user, events)
    return Response(content=ics_bytes, media_type="text/calendar; charset=utf-8")
