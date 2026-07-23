import uuid
from datetime import UTC, date, datetime, timedelta
from statistics import mean, median

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cc_crm.core.errors import ConflictError
from cc_crm.core.time import naive_utc
from cc_crm.models.activity import Activity
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import InvoiceStatus, SubmissionStatus, TaskStatus
from cc_crm.models.operational import Document, EmailDraftLog, SourcingMetric
from cc_crm.models.recruiting import Fee, Offer, Placement
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.task import Task
from cc_crm.repositories.operational import (
    DocumentRepository,
    EmailDraftRepository,
    SourcingMetricRepository,
)
from cc_crm.schemas.operational import (
    DocumentCreate,
    EmailDraftCreate,
    SourcingMetricCreate,
)
from cc_crm.services.base import CrudService
from cc_crm.services.storage import has_generic_filename


class EmptyUpdate(BaseModel):
    pass


class DocumentService(CrudService[Document, DocumentCreate, EmptyUpdate]):
    def __init__(self, session: Session) -> None:
        repository = DocumentRepository(session)
        super().__init__(session, repository, "Document")
        self.documents = repository

    def create(self, payload: DocumentCreate) -> Document:
        values = payload.model_dump(exclude_none=True)
        values["has_generic_filename"] = has_generic_filename(payload.filename)
        try:
            entity = self.repository.create(values)
            self.session.commit()
            return entity
        except IntegrityError as exception:
            self.session.rollback()
            raise ConflictError(f"{self.entity_name} conflicts with existing data") from exception
        except Exception:
            self.session.rollback()
            raise


class SourcingMetricService(CrudService[SourcingMetric, SourcingMetricCreate, EmptyUpdate]):
    def __init__(self, session: Session) -> None:
        repository = SourcingMetricRepository(session)
        super().__init__(session, repository, "SourcingMetric")
        self.metrics = repository

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator * 100, 1) if denominator else None

    def totals_for_period(self, period_start: date, period_end: date) -> dict[str, object]:
        """Summiert alle manuell erfassten SourcingMetric-Datensaetze, deren
        Zeitraum sich mit [period_start, period_end] ueberschneidet. has_data
        ist False, solange noch keine einzige Erfassung vorliegt - die
        Analytics-Seite zeigt dann "Keine Daten erfasst" statt einer Zahl."""
        entries = self.metrics.in_period(period_start, period_end)
        pitches = sum(entry.pitches for entry in entries)
        responses = sum(entry.responses for entry in entries)
        positive_responses = sum(entry.positive_responses for entry in entries)
        qualification_calls = sum(entry.qualification_calls for entry in entries)
        return {
            "has_data": len(entries) > 0,
            "pitches": pitches,
            "responses": responses,
            "positive_responses": positive_responses,
            "qualification_calls": qualification_calls,
            "pitch_to_response_rate": self._rate(responses, pitches),
            "response_to_qualification_call_rate": self._rate(qualification_calls, responses),
        }


class EmailWorkflowService:
    # (key, name, subject, body) - jede Vorlage hat einen eigenen, auf ihren
    # Anlass zugeschnittenen body-Text (vorher lieferte templates() fuer
    # jeden Key denselben generischen Fliesstext, nur der subject
    # unterschied sich - Nutzer-Feedback: das reicht fuer die gewuenschten
    # Vorlagen nicht aus). Adressat (Kandidat vs. Kanzlei-Kontakt) ergibt
    # sich aus dem jeweiligen body-Text selbst.
    TEMPLATES = [
        (
            "post_qualification_call",
            "Nach Quali Call",
            "Vielen Dank für das Gespräch, {candidate}",
            "Guten Tag {candidate},\n\n"
            "vielen Dank für das offene und informative Gespräch eben. Ich habe ein gutes Bild "
            "von Ihrem Profil und Ihren Vorstellungen gewinnen können.\n\n"
            "Nächster Schritt: {next_step}\n\n"
            "Ich melde mich, sobald es Neuigkeiten gibt. Bei Rückfragen erreichen Sie mich "
            "jederzeit.\n\nBeste Grüße",
        ),
        (
            "request_cv",
            "CV nachfordern",
            "Unterlagen zu Ihrem Profil",
            "Guten Tag {candidate},\n\n"
            "um Ihr Profil vollständig vorstellen zu können, fehlen mir noch aktuelle "
            "Unterlagen (Lebenslauf/Zeugnisse). Könnten Sie mir diese bei Gelegenheit "
            "zusenden?\n\nVielen Dank und beste Grüße",
        ),
        (
            "profile_approval",
            "Kurzprofil freigeben",
            "Freigabe Ihres Kurzprofils",
            "Guten Tag {candidate},\n\n"
            "anbei finden Sie das anonymisierte Kurzprofil, das ich potenziellen Kanzleien "
            "vorstellen möchte:\n\n{short_profile}\n\n"
            "Bitte prüfen Sie den Text kurz und geben Sie mir Bescheid, ob ich ihn so "
            "verwenden darf oder ob noch etwas angepasst werden soll.\n\nBeste Grüße",
        ),
        (
            "candidate_submission",
            "CV-Out Vorstellung",
            "Profilvorstellung: {candidate} – {role}",
            "Guten Tag {contact},\n\n"
            "ich möchte Ihnen folgendes Profil für die Position {role} vorstellen:\n\n"
            "{short_profile}\n\n"
            "Gehaltsvorstellung: {salary}\n"
            "Kündigungsfrist: {notice_period}\n\n"
            "Die vollständigen Unterlagen finden Sie im Anhang. Über Ihre Rückmeldung, ob Sie "
            "{candidate} kennenlernen möchten, freue ich mich.\n\nBeste Grüße",
        ),
        (
            "submission_follow_up",
            "CV-Out nachfassen",
            "Feedback zu {candidate}",
            "Guten Tag {contact},\n\n"
            "ich wollte kurz nachfragen, ob Sie das Profil von {candidate} bereits prüfen "
            "konnten und ob Interesse an einem Kennenlernen besteht.\n\n"
            "Über eine kurze Rückmeldung würde ich mich freuen.\n\nBeste Grüße",
        ),
        (
            "interview_confirmation",
            "Interview bestätigen",
            "Interviewtermin bei {client}",
            "Guten Tag {contact},\n\n"
            "hiermit bestätige ich den vereinbarten Interviewtermin für {candidate} bei "
            "{client}.\n\nNächster Schritt: {next_step}\n\n"
            "Bitte geben Sie mir Bescheid, falls sich am Termin noch etwas ändert.\n\n"
            "Beste Grüße",
        ),
        (
            "interview_feedback",
            "Interviewfeedback nachfassen (Kanzlei)",
            "Kurzes Feedback zum Interview mit {candidate}",
            "Guten Tag {contact},\n\n"
            "wie war Ihr Eindruck vom Gespräch mit {candidate}? Über eine kurze Rückmeldung "
            "- positiv wie kritisch - würde ich mich freuen, damit wir den Prozess zeitnah "
            "fortsetzen können.\n\nBeste Grüße",
        ),
        (
            "interview_feedback_candidate",
            "Interviewfeedback nachfassen (Kandidat)",
            "Rückmeldung zu Ihrem Interview bei {client}",
            "Guten Tag {candidate},\n\n"
            "vielen Dank, dass Sie sich Zeit für das Gespräch bei {client} genommen haben. "
            "Ich wollte kurz nachfragen, wie Sie das Interview erlebt haben, und Sie über den "
            "aktuellen Stand informieren.\n\nNächster Schritt: {next_step}\n\nBeste Grüße",
        ),
        (
            "offer_follow_up",
            "Offer nachfassen",
            "Abstimmung zum Angebot",
            "Guten Tag {contact},\n\n"
            "wie ist der aktuelle Stand beim Angebot für {candidate}? Gibt es von Ihrer Seite "
            "noch offene Punkte, die wir gemeinsam klären sollten?\n\nBeste Grüße",
        ),
        (
            "candidate_rejection",
            "Absage Kandidat",
            "Rückmeldung zum Prozess",
            "Guten Tag {candidate},\n\n"
            "leider muss ich Ihnen mitteilen, dass sich {client} für einen anderen "
            "Kandidaten entschieden hat. Ich weiß, das ist keine schöne Nachricht.\n\n"
            "Ich halte weiterhin Ausschau nach passenden Positionen für Sie und melde mich, "
            "sobald es Neuigkeiten gibt.\n\nBeste Grüße",
        ),
        (
            "client_rejection",
            "Absage Kunde",
            "Rückmeldung zu {candidate}",
            "Guten Tag {contact},\n\n"
            "{candidate} hat sich nach reiflicher Überlegung gegen die Position bei {client} "
            "entschieden.\n\nIch halte Sie über weitere passende Profile gerne auf dem "
            "Laufenden.\n\nBeste Grüße",
        ),
        (
            "send_terms",
            "AGB senden",
            "Zusammenarbeit mit CC",
            "Guten Tag {contact},\n\n"
            "vielen Dank für Ihr Interesse an einer Zusammenarbeit. Anbei erhalten Sie "
            "unsere Allgemeinen Geschäftsbedingungen zur Prüfung und Unterschrift.\n\n"
            "Bei Rückfragen stehe ich Ihnen gerne zur Verfügung.\n\nBeste Grüße",
        ),
        (
            "placement_invoice",
            "Placement / Rechnung",
            "Erfolgreiche Besetzung",
            "Guten Tag {contact},\n\n"
            "vielen Dank für die gute Zusammenarbeit - die Position ist mit {candidate} "
            "erfolgreich besetzt. Die Rechnung zur vereinbarten Vermittlungsprovision "
            "erhalten Sie anbei.\n\nBeste Grüße",
        ),
    ]

    def __init__(self, session: Session) -> None:
        self.session = session
        self.drafts = EmailDraftRepository(session)

    def templates(self) -> list[dict[str, object]]:
        placeholders = [
            "candidate",
            "client",
            "contact",
            "role",
            "salary",
            "notice_period",
            "short_profile",
            "next_step",
        ]
        return [
            {
                "key": key,
                "name": name,
                "subject": subject,
                "body": body,
                "placeholders": placeholders,
            }
            for key, name, subject, body in self.TEMPLATES
        ]

    def create_draft(self, payload: EmailDraftCreate) -> EmailDraftLog:
        draft = self.drafts.create(
            {
                **payload.model_dump(exclude_none=True),
                "provider": "outlook",
                "drafted_at": datetime.now(UTC),
            }
        )
        self.session.commit()
        return draft


class CockpitService:
    HOT = {
        SubmissionStatus.INTERVIEW,
        SubmissionStatus.OFFER,
        SubmissionStatus.PLACEMENT,
    }

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator * 100, 1) if denominator else 0.0

    def _candidate_names(self, candidate_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not candidate_ids:
            return {}
        rows = self.session.execute(
            select(Candidate.id, Candidate.first_name, Candidate.last_name).where(
                Candidate.id.in_(candidate_ids)
            )
        ).all()
        return {row.id: f"{row.first_name} {row.last_name}" for row in rows}

    def _client_names(self, client_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not client_ids:
            return {}
        rows = self.session.execute(
            select(ClientCompany.id, ClientCompany.name).where(ClientCompany.id.in_(client_ids))
        ).all()
        return {row.id: row.name for row in rows}

    @staticmethod
    def _hot_title(
        submission: CandidateSubmission,
        candidate_names: dict[uuid.UUID, str],
        client_names: dict[uuid.UUID, str],
    ) -> str:
        """z.B. "Interview — Max Mustermann bei ACME GmbH" statt nur "Interview"."""
        status_label = submission.status.value.replace("_", " ").title()
        candidate_name = candidate_names.get(submission.candidate_id)
        if candidate_name is None:
            return status_label
        client_name = (
            client_names.get(submission.client_company_id) if submission.client_company_id else None
        )
        who = f"{candidate_name} bei {client_name}" if client_name else candidate_name
        return f"{status_label} — {who}"

    def build(self, period: str) -> dict[str, object]:
        now = naive_utc(datetime.now(UTC))
        since = now - timedelta(days={"week": 7, "month": 30, "quarter": 90}.get(period, 7))
        due_soon = now + timedelta(days=1)
        submissions = list(self.session.scalars(select(CandidateSubmission)).all())
        tasks = list(
            self.session.scalars(
                select(Task).where(Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]))
            ).all()
        )
        # KEIN select(Interview) hier - die separate Interview-Tabelle
        # (Termin-/Feedback-Verwaltung, siehe services/recruiting.py) wird in
        # der Praxis nicht gepflegt und blieb deshalb dauerhaft leer, obwohl
        # das Kanban laengst Submissions mit Status INTERVIEW zeigte
        # ("Interviews: 0" in Analytics vs. echte Prozesse im Kanban - siehe
        # Nutzer-Feedback 2026-07-15). "Interviews" zaehlt deshalb jetzt den
        # echten, aktuellen Submission-Status - konsistent mit dem Kanban.
        interviews_in_progress = [
            item for item in submissions if item.status == SubmissionStatus.INTERVIEW
        ]
        reached_interview_stage = {
            SubmissionStatus.INTERVIEW,
            SubmissionStatus.OFFER,
            SubmissionStatus.PLACEMENT,
        }
        offers = [
            item
            for item in self.session.scalars(select(Offer)).all()
            if naive_utc(item.created_at) >= since
        ]
        placements = [
            item
            for item in self.session.scalars(select(Placement)).all()
            if naive_utc(item.created_at) >= since
        ]
        fees = [
            item
            for item in self.session.scalars(select(Fee)).all()
            if naive_utc(item.created_at) >= since
        ]
        period_submissions = [item for item in submissions if naive_utc(item.created_at) >= since]
        due_tasks = [
            task for task in tasks if task.due_at is None or naive_utc(task.due_at) <= due_soon
        ]
        hot_submissions = [item for item in submissions if item.status in self.HOT]

        # Namen fuer Kandidat/Kanzlei in einem Bulk-Query je Entitaet statt pro
        # Zeile nachzuladen (kein ORM relationship() in diesem Codebase, daher
        # kein selectinload moeglich - bulk IN-Query erreicht denselben Zweck:
        # konstante statt mit der Datenmenge wachsende Query-Anzahl).
        candidate_ids = {task.candidate_id for task in due_tasks if task.candidate_id} | {
            item.candidate_id for item in hot_submissions
        }
        client_ids = {task.client_company_id for task in due_tasks if task.client_company_id} | {
            item.client_company_id for item in hot_submissions if item.client_company_id
        }
        candidate_names = self._candidate_names(candidate_ids)
        client_names = self._client_names(client_ids)

        important = [
            {
                "kind": "task",
                "title": task.title,
                "detail": " — ".join(
                    filter(
                        None,
                        [
                            candidate_names.get(task.candidate_id) if task.candidate_id else None,
                            client_names.get(task.client_company_id)
                            if task.client_company_id
                            else None,
                            task.description or "Offene Aufgabe",
                        ],
                    )
                ),
                "due_at": task.due_at,
                "candidate_id": task.candidate_id,
                "client_company_id": task.client_company_id,
                "submission_id": task.candidate_submission_id,
                "priority": task.priority.value,
            }
            for task in due_tasks
        ]
        hot = [
            {
                "kind": "submission",
                "title": self._hot_title(item, candidate_names, client_names),
                "detail": item.next_step or "Nächsten Schritt abstimmen",
                "due_at": item.follow_up_at,
                "candidate_id": item.candidate_id,
                "client_company_id": item.client_company_id,
                "submission_id": item.id,
                "priority": "high",
            }
            for item in hot_submissions
        ]
        paid = sum(1 for fee in fees if fee.invoice_status == InvoiceStatus.PAID)
        expected = sum(float(item.expected_fee or 0) for item in submissions)
        realized = sum(
            float(fee.amount_net) for fee in fees if fee.invoice_status == InvoiceStatus.PAID
        )
        cv_count = (
            self.session.scalar(
                select(func.count())
                .select_from(Candidate)
                .where(Candidate.cv_in_recorded_at.isnot(None))
            )
            or 0
        )
        reached_interview_in_period = [
            item for item in period_submissions if item.status in reached_interview_stage
        ]
        sourcing = SourcingMetricService(self.session).totals_for_period(since.date(), now.date())
        return {
            "period": period,
            "important": important,
            "hot_processes": hot,
            "sourcing": sourcing,
            "recruiting_kpis": self._recruiting_kpis(),
            "kpis": {
                "qualification_calls": len(period_submissions),
                "cv_available": cv_count,
                "submissions": len(period_submissions),
                "interviews": len(interviews_in_progress),
                "offers": len(offers),
                "placements": len(placements),
                "expected_fees": expected,
                "realized_fees": realized,
            },
            "rates": {
                "submission_to_interview": self._rate(
                    len(reached_interview_in_period), len(period_submissions)
                ),
                "interview_to_offer": self._rate(len(offers), len(reached_interview_in_period)),
                "offer_to_placement": self._rate(len(placements), len(offers)),
                "placement_to_paid": self._rate(paid, len(placements)),
            },
        }

    def _recruiting_kpis(self) -> dict[str, float | None]:
        """Etablierte Standard-Recruiting-Kennzahlen ueber den GESAMTEN
        historischen Bestand (nicht auf den period-Zeitraum beschraenkt -
        ein Median ueber nur eine Woche/einen Monat haette zu wenige
        Datenpunkte, um aussagekraeftig zu sein)."""
        all_submissions = {
            row.id: row for row in self.session.scalars(select(CandidateSubmission)).all()
        }
        placements = list(self.session.scalars(select(Placement)).all())

        fill_days = [
            (naive_utc(placement.created_at) - naive_utc(submission.created_at)).days
            for placement in placements
            if (submission := all_submissions.get(placement.submission_id)) is not None
        ]

        # Time-to-Interview: Submission-Erstellung bis zum Activity-Eintrag,
        # der den Uebergang IN "interview" protokolliert (siehe
        # services/submissions.py::transition(), Activity.details ist immer
        # "{alter_status} -> {neuer_status}" mit optionalem ": {grund}"-
        # Suffix nur bei Abbruch/Storno-Transitionen).
        interview_activities = list(
            self.session.scalars(
                select(Activity).where(
                    Activity.activity_type == "submission_status_changed",
                    Activity.details.like("%-> interview"),
                )
            ).all()
        )
        interview_days = [
            (naive_utc(activity.occurred_at) - naive_utc(submission.created_at)).days
            for activity in interview_activities
            if activity.candidate_submission_id is not None
            and (submission := all_submissions.get(activity.candidate_submission_id)) is not None
        ]

        fees = [float(placement.calculated_fee) for placement in placements]

        return {
            "time_to_fill_days": median(fill_days) if fill_days else None,
            "time_to_interview_days": median(interview_days) if interview_days else None,
            "average_fee_per_placement": round(mean(fees), 2) if fees else None,
        }

    def profile_suggestion(self, candidate_id: uuid.UUID) -> str:
        candidate = self.session.get(Candidate, candidate_id)
        if candidate is None:
            from cc_crm.core.errors import EntityNotFoundError

            raise EntityNotFoundError("Candidate not found")
        role = candidate.job_title or "qualifizierte Fachkraft"
        region = candidate.city or candidate.postal_code or "Deutschland"
        parts = [
            f"{candidate.first_name} {candidate.last_name} ist als {role} tätig.",
            f"Der regionale Fokus liegt auf {region}.",
        ]
        if candidate.qualification:
            parts.append(f"Qualifikation: {candidate.qualification}.")
        if candidate.summary:
            parts.append(candidate.summary)
        return " ".join(parts)
