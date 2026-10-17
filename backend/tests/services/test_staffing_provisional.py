# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Vorlaeufige Fristen: geplanter (nicht aktivierter) Einsatz oder Einsatz ohne Enddatum."""

from datetime import date

from sqlalchemy.orm import Session

from cc_crm.models.staffing import StaffingAssignmentStatus
from cc_crm.services.staffing_deadline_job import pair_deadline
from cc_crm.services.staffing_deadlines import Span, Traffic, compute_deadline, merge_spans
from tests.services.test_staffing_deadline_job import (
    _assignment,
    _client,
    _worker,
    session,
)

D = date
_ = session  # Fixture (per Import registriert)
TODAY = D(2026, 6, 1)


# --- Rechenkern ----------------------------------------------------------------------------


def test_chain_of_closed_known_spans_is_final() -> None:
    result = compute_deadline(
        [Span(D(2026, 1, 1), D(2026, 2, 28)), Span(D(2026, 3, 15), D(2026, 7, 31))], TODAY
    )
    assert result.has_chain and not result.provisional
    assert result.provisional_reasons == ()


def test_planned_assignment_makes_the_chain_provisional() -> None:
    result = compute_deadline([Span(D(2026, 1, 1), D(2026, 12, 31), planned=True)], TODAY)
    assert result.provisional
    assert result.provisional_reasons == ("planned_assignment",)


def test_open_end_makes_the_chain_provisional() -> None:
    result = compute_deadline([Span(D(2026, 1, 1), None)], TODAY)
    assert result.provisional
    assert result.provisional_reasons == ("open_end",)


def test_both_reasons_are_reported() -> None:
    result = compute_deadline(
        [Span(D(2026, 1, 1), None), Span(D(2026, 2, 1), D(2026, 3, 1), planned=True)], TODAY
    )
    assert result.provisional_reasons == ("planned_assignment", "open_end")


def test_planned_flag_survives_merging_even_inside_an_open_span() -> None:
    merged = merge_spans(
        [Span(D(2026, 1, 1), None), Span(D(2026, 3, 1), D(2026, 4, 1), planned=True)]
    )
    assert merged == [Span(D(2026, 1, 1), None, planned=True)]
    merged = merge_spans(
        [Span(D(2026, 1, 1), D(2026, 2, 1)), Span(D(2026, 2, 2), D(2026, 3, 1), True)]
    )
    assert len(merged) == 1 and merged[0].planned and merged[0].end == D(2026, 3, 1)


def test_a_planned_span_in_an_earlier_chain_does_not_count() -> None:
    # Luecke > 3 Monate: der alte Zaehler ist zurueckgesetzt, nur die aktuelle Kette zaehlt
    result = compute_deadline(
        [
            Span(D(2025, 1, 1), D(2025, 2, 1), planned=True),
            Span(D(2026, 1, 1), D(2026, 7, 31)),
        ],
        TODAY,
    )
    assert result.chain_start == D(2026, 1, 1)
    assert not result.provisional


def test_prior_periods_alone_never_make_it_provisional() -> None:
    result = compute_deadline(
        [Span(D(2026, 3, 1), D(2026, 7, 31))],
        TODAY,
        prior_spans=[Span(D(2025, 11, 1), D(2026, 2, 1))],
    )
    assert result.prior_days > 0 and not result.provisional


def test_traffic_light_is_unchanged_by_provisional() -> None:
    spans = [Span(D(2025, 1, 1), None)]  # 17 Monate: rot/gelb je nach Stichtag
    open_result = compute_deadline(spans, D(2026, 5, 15))
    closed_result = compute_deadline([Span(D(2025, 1, 1), D(2026, 5, 15))], D(2026, 5, 15))
    assert open_result.provisional and not closed_result.provisional
    assert open_result.traffic == closed_result.traffic == Traffic.YELLOW


# --- aus der Datenbank -----------------------------------------------------------------------


def test_pair_deadline_marks_planned_and_open_ended_assignments(session: Session) -> None:
    worker, client = _worker(session), _client(session)
    active = _assignment(session, worker, client, D(2026, 1, 1), end=D(2026, 12, 31))
    result = pair_deadline(session, worker.id, client.id, TODAY)
    assert not result.provisional  # aktiv mit bekanntem Ende

    _assignment(
        session,
        worker,
        client,
        D(2026, 7, 1),
        end=D(2026, 9, 30),
        status=StaffingAssignmentStatus.PLANNED,
    )
    result = pair_deadline(session, worker.id, client.id, TODAY)
    assert result.provisional_reasons == ("planned_assignment",)

    active.planned_end_date = None  # Enddatum nicht erfasst
    session.commit()
    result = pair_deadline(session, worker.id, client.id, TODAY)
    assert result.provisional_reasons == ("planned_assignment", "open_end")


def test_overdue_active_assignment_counts_as_open_end(session: Session) -> None:
    worker, client = _worker(session), _client(session)
    _assignment(session, worker, client, D(2026, 1, 1), end=D(2026, 2, 28))  # aktiv, ueberfaellig
    result = pair_deadline(session, worker.id, client.id, TODAY)
    assert result.provisional_reasons == ("open_end",)
