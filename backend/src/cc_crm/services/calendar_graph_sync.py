"""Bidirektionaler Kalender-Sync zwischen CalendarEvent (pro Nutzer) und dem
Microsoft-365-Kalender des Postfachs, das dieser Nutzer per OAuth verbunden
hat (Auftrag "M365-Postfach-Integration", Nutzer-Entscheidung: pro Nutzer,
kein gemeinsamer Firmenkalender - siehe MailAccount.oauth_connected_by_user_id).

Konfliktloesung: Last-Write-Wins per Zeitstempel (CalendarEvent.updated_at
vs. Graphs lastModifiedDateTime), verglichen gegen
external_graph_last_synced_at (siehe sync_account_calendar unten).
Loeschungen: CRM->Graph synchron beim Loeschen (siehe
push_delete_to_graph, aufgerufen aus CalendarEventService.delete_for_user);
Graph->CRM ueber den @removed-Marker der Delta-Query (siehe
_apply_graph_removals)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.time import naive_utc
from cc_crm.integrations.microsoft_graph.client import (
    GraphApiError,
    create_event,
    delete_event,
    fetch_calendar_delta,
    update_event,
)
from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.enums import MailAccountProvider
from cc_crm.models.mail import MailAccount
from cc_crm.services.graph_token_service import get_valid_access_token

logger = logging.getLogger("cc_crm.calendar_graph_sync")


def push_delete_to_graph(session: Session, event: CalendarEvent) -> None:
    """Best effort, synchron beim Loeschen eines CalendarEvent aufgerufen -
    ein transienter Graph-Fehler blockiert die vom Nutzer gewuenschte
    CRM-Loeschung NICHT (siehe M365-Integrationsplan, Abschnitt
    Kalender-Konfliktlogik), wird aber geloggt."""
    if not event.external_graph_event_id:
        return
    account = _account_for_user(session, event.owner_user_id)
    if account is None:
        return
    try:
        access_token = get_valid_access_token(session, account)
        delete_event(access_token, graph_event_id=event.external_graph_event_id)
    except Exception:  # noqa: BLE001 - Loeschung im CRM darf nicht daran scheitern
        logger.warning(
            "Graph-Loeschung von Event %s (Postfach %s) fehlgeschlagen - CRM-Termin "
            "wird trotzdem geloescht.",
            event.external_graph_event_id,
            account.address,
            exc_info=True,
        )


def _account_for_user(session: Session, user_id: object) -> MailAccount | None:
    return session.scalar(
        select(MailAccount).where(
            MailAccount.provider == MailAccountProvider.MICROSOFT_GRAPH,
            MailAccount.oauth_connected_by_user_id == user_id,
            MailAccount.is_active.is_(True),
        )
    )


def sync_account_calendar(session: Session, account: MailAccount) -> None:
    """Ein Durchlauf fuer EIN Postfach - Einstiegspunkt fuer den
    zeitgesteuerten Lauf (siehe jobs/graph_sync.py). Reihenfolge bewusst:
    erst lokale Aenderungen/Neuanlagen nach Graph pushen, DANACH Graph-Delta
    abholen - so landet eine soeben von hier aus angelegte Graph-ID nicht
    faelschlich als "neu von Graph" in derselben Runde."""
    if account.oauth_connected_by_user_id is None:
        return
    access_token = get_valid_access_token(session, account)
    _push_local_changes(session, access_token, account)
    _pull_graph_changes(session, access_token, account)


def _push_local_changes(session: Session, access_token: str, account: MailAccount) -> None:
    events = session.scalars(
        select(CalendarEvent).where(
            CalendarEvent.owner_user_id == account.oauth_connected_by_user_id
        )
    ).all()
    for event in events:
        try:
            if event.external_graph_event_id is None:
                graph_id = create_event(
                    access_token,
                    title=event.title,
                    body_text=event.notes,
                    start_at=event.start_at,
                    end_at=event.end_at,
                    location=event.location,
                )
                event.external_graph_event_id = graph_id
                event.external_graph_last_synced_at = event.updated_at
            elif event.external_graph_last_synced_at is None or naive_utc(
                event.updated_at
            ) > naive_utc(event.external_graph_last_synced_at):
                # Nur pushen, wenn die CRM-Seite seit dem letzten Abgleich
                # tatsaechlich geaendert wurde - sonst wuerde jeder Lauf
                # jedes Event erneut ueberschreiben, auch ohne Aenderung.
                update_event(
                    access_token,
                    graph_event_id=event.external_graph_event_id,
                    title=event.title,
                    body_text=event.notes,
                    start_at=event.start_at,
                    end_at=event.end_at,
                    location=event.location,
                )
                event.external_graph_last_synced_at = event.updated_at
        except GraphApiError:
            logger.warning(
                "Push von CalendarEvent %s nach Graph fehlgeschlagen", event.id, exc_info=True
            )
    session.commit()


def _pull_graph_changes(session: Session, access_token: str, account: MailAccount) -> None:
    result = fetch_calendar_delta(access_token, delta_link=account.graph_calendar_delta_link)
    for graph_event in result.events:
        event = session.scalar(
            select(CalendarEvent).where(CalendarEvent.external_graph_event_id == graph_event.id)
        )
        if event is None:
            # Neues Event auf Graph-Seite, das hier noch nicht bekannt ist -
            # als neuer CRM-Termin fuer den verbindenden Nutzer anlegen.
            event = CalendarEvent(
                title=graph_event.subject,
                start_at=graph_event.start_at,
                end_at=graph_event.end_at,
                notes=graph_event.body_text,
                location=graph_event.location,
                owner_user_id=account.oauth_connected_by_user_id,
                created_by_user_id=account.oauth_connected_by_user_id,
                external_graph_event_id=graph_event.id,
                external_graph_last_synced_at=graph_event.last_modified_at,
            )
            session.add(event)
            continue

        # Last-Write-Wins: nur uebernehmen, wenn Graph seit dem letzten
        # Abgleich tatsaechlich neuer ist als die CRM-Version - sonst
        # wuerde ein reiner Re-Poll ohne echte Aenderung eine gerade lokal
        # gemachte, noch nicht gepushte Aenderung wieder ueberschreiben.
        graph_synced_at = (
            naive_utc(event.external_graph_last_synced_at)
            if event.external_graph_last_synced_at is not None
            else None
        )
        if graph_synced_at is None or naive_utc(graph_event.last_modified_at) > graph_synced_at:
            if naive_utc(event.updated_at) > (graph_synced_at or naive_utc(event.updated_at)):
                logger.info(
                    "Kalender-Konflikt bei Event %s: beide Seiten geaendert, Graph-Stand "
                    "(%s) gewinnt gegenueber CRM-Stand (%s).",
                    event.id,
                    graph_event.last_modified_at,
                    event.updated_at,
                )
            event.title = graph_event.subject
            event.start_at = graph_event.start_at
            event.end_at = graph_event.end_at
            event.notes = graph_event.body_text
            event.location = graph_event.location
            event.external_graph_last_synced_at = graph_event.last_modified_at

    if result.removed_ids:
        session.query(CalendarEvent).filter(
            CalendarEvent.external_graph_event_id.in_(result.removed_ids)
        ).delete(synchronize_session=False)

    if result.delta_link:
        account.graph_calendar_delta_link = result.delta_link
    session.commit()
