# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Deckt der verknüpfte Überlassungsvertrag (§ 12 AÜG) den Einsatz ab?

Gilt als abgedeckt, wenn am Einsatz ein Vertrag des RICHTIGEN Kunden hängt, der aktiv ist,
spätestens am Einsatzbeginn beginnt (`valid_from <= Beginn`, ohne Gültig-ab gilt er als nicht
belegt) und bis zum Ende des geprüften Zeitraums reicht (`valid_to` leer oder `>= Ende`). Der
Zeitraum ist derselbe wie bei der Erlaubnisprüfung: Beginn bis geplantes Ende, ohne Plan bis heute.

Die Prüfung ist eine reine Funktion ohne Datenbank. Daraus ergeben sich der Aktivierungsfehler, der
(abgeleitete) Checklistenpunkt "Überlassungsvertrag" und der Hinweis bei einer späteren Lücke."""

from datetime import date

from cc_crm.models.staffing import StaffingAssignment, StaffingContract, StaffingContractStatus

CONTRACT_STATUS_LABELS = {
    StaffingContractStatus.DRAFT: "Entwurf",
    StaffingContractStatus.ACTIVE: "aktiv",
    StaffingContractStatus.EXPIRED: "abgelaufen",
    StaffingContractStatus.TERMINATED: "gekündigt",
}


def _fmt(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def assignment_period_end(assignment: StaffingAssignment, today: date) -> date:
    """Ende des geprüften Zeitraums (wie bei der AÜG-Erlaubnis)."""
    return assignment.planned_end_date or max(assignment.start_date, today)


def supply_contract_problem(
    assignment: StaffingAssignment, contract: StaffingContract | None, today: date
) -> str | None:
    """`None`, wenn der Vertrag den Einsatz abdeckt, sonst die Meldung auf Deutsch."""
    if assignment.contract_id is None or contract is None:
        return "Kein Überlassungsvertrag am Einsatz verknüpft (§ 12 AÜG)."
    reference = contract.contract_number or "ohne Nummer"
    if contract.client_company_id != assignment.client_company_id:
        return f"Der Überlassungsvertrag {reference} gehört zu einem anderen Kunden."
    if contract.status != StaffingContractStatus.ACTIVE:
        return (
            f"Der Überlassungsvertrag {reference} ist nicht aktiv "
            f"(Status: {CONTRACT_STATUS_LABELS[contract.status]})."
        )
    if contract.valid_from is None:
        return f"Beim Überlassungsvertrag {reference} ist kein Gültig-ab hinterlegt."
    if contract.valid_from > assignment.start_date:
        return (
            f"Der Überlassungsvertrag {reference} gilt erst ab {_fmt(contract.valid_from)}, "
            f"der Einsatz beginnt am {_fmt(assignment.start_date)}."
        )
    period_end = assignment_period_end(assignment, today)
    if contract.valid_to is not None and contract.valid_to < period_end:
        return (
            f"Der Überlassungsvertrag {reference} läuft am {_fmt(contract.valid_to)} ab, "
            f"der Einsatz läuft bis {_fmt(period_end)}."
        )
    return None
