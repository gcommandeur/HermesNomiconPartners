import re
import uuid
from collections.abc import Collection
from datetime import UTC, date, datetime, timedelta
from statistics import mean, median
from typing import Any

from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cc_crm.core.errors import ConflictError, EntityNotFoundError
from cc_crm.core.time import naive_utc
from cc_crm.models.activity import Activity
from cc_crm.models.candidate import Candidate
from cc_crm.models.candidate_pitch_log import CandidatePitchLog
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.email_template import EmailTemplate
from cc_crm.models.enums import InvoiceStatus, SubmissionStatus, TaskStatus
from cc_crm.models.operational import Document, EmailDraftLog, SourcingMetric
from cc_crm.models.recruiting import Fee, Offer, Placement
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.task import Task
from cc_crm.repositories.email_templates import EmailTemplateRepository
from cc_crm.repositories.operational import (
    DocumentRepository,
    EmailDraftRepository,
    SourcingMetricRepository,
)
from cc_crm.schemas.operational import (
    DocumentCreate,
    EmailDraftCreate,
    EmailTemplateUpdate,
    SourcingMetricCreate,
)
from cc_crm.services.base import CrudService
from cc_crm.services.recruiting import stage_reached_counts
from cc_crm.services.storage import has_generic_filename

# {candidate}, {candidate_number}, ... - erfasst jedes {wort} literal, keine
# verschachtelten/format-spec-Platzhalter (nicht gebraucht, siehe
# EmailTemplate-Docstring).
PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


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
            self._mark_cv_available_if_needed(entity)
            self.session.commit()
            return entity
        except IntegrityError as exception:
            self.session.rollback()
            raise ConflictError(f"{self.entity_name} conflicts with existing data") from exception
        except Exception:
            self.session.rollback()
            raise

    def _mark_cv_available_if_needed(self, document: Document) -> None:
        """Setzt Candidate.cv_available (+ cv_in_recorded_at), sobald ein
        CV-Dokument fuer diesen Kandidaten hochgeladen wird - zentral hier
        statt im API-Endpunkt (api/v1/operational.py::upload_document),
        damit es unabhaengig vom Aufruf-Pfad greift (z.B. auch fuer
        kuenftige Upload-Wege). Bugfix "CV-Dokument-Upload setzt
        cv_available nicht": die documents-Tabelle (echte Datei-Uploads,
        document_type='cv') ist komplett getrennt vom reinen Anzeige-/
        Analytics-Flag Candidate.cv_available - ein hochgeladenes CV setzte
        dieses Flag bisher NIE automatisch, "CV In" haengt bislang
        ausschliesslich vom manuellen Anhaken der Checkbox im Bearbeiten-
        Formular ab (Live-Befund Produktion: 9 Kandidaten mit CV-Dokument,
        aber cv_available=False, u.a. der urspruenglich gemeldete Fall
        Lorenz Hafner). Ergaenzt die beiden bestehenden Stempel-Pfade
        (CandidateService.create()/update()) um einen dritten, bisher
        fehlenden - alle drei bleiben unveraendert bestehen.

        Idempotent: greift nur, wenn cv_available noch False ist (kein
        erneutes Ueberschreiben bei einem zweiten CV-Upload desselben
        Kandidaten) bzw. nur, wenn cv_in_recorded_at noch None ist."""
        if document.owner_type != "candidate" or document.document_type != "cv":
            return
        candidate = self.session.get(Candidate, document.owner_id)
        if candidate is None:
            return
        if not candidate.cv_available:
            candidate.cv_available = True
        if candidate.cv_in_recorded_at is None:
            candidate.cv_in_recorded_at = datetime.now(UTC)


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
    """Mail-Vorlagen wurden aus dieser Klasse in die DB-Tabelle
    `email_templates` verlagert (Auftrag "Mailvorlagen editierbar machen",
    Alembic-Revision d4e5f6a7b8c9), damit Name/Betreff/Text ohne Deploy im CRM
    bearbeitet werden koennen - siehe models/email_template.py::EmailTemplate.
    Die vormals hier hartcodierte TEMPLATES-Liste (13 Vorlagen) wurde 1:1 in
    die Migration als Seed-Daten uebernommen; `templates()` liest jetzt aus
    `self.templates_repo` statt aus einer Python-Konstante."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.drafts = EmailDraftRepository(session)
        self.templates_repo = EmailTemplateRepository(session)

    @staticmethod
    def extract_placeholders(subject: str, body: str) -> list[str]:
        """Liest die tatsaechlich verwendeten {token}-Platzhalter aus subject+
        body (Reihenfolge des ersten Vorkommens, keine Duplikate) - ersetzt
        die vorherige statische, fuer alle Vorlagen identische Liste, die
        Platzhalter zeigte, die eine Vorlage gar nicht benutzte."""
        seen: dict[str, None] = {}
        for match in PLACEHOLDER_RE.findall(f"{subject}\n{body}"):
            seen.setdefault(match, None)
        return list(seen)

    def templates(self) -> list[dict[str, object]]:
        return [
            {
                "key": template.key,
                "name": template.name,
                "subject": template.subject,
                "body": template.body,
                "placeholders": self.extract_placeholders(template.subject, template.body),
            }
            for template in self.templates_repo.list_all()
        ]

    def update_template(self, key: str, payload: EmailTemplateUpdate) -> EmailTemplate:
        """PATCH /operational/email-templates/{key} - `key` selbst ist bewusst
        nicht Teil von EmailTemplateUpdate (siehe dortiger Docstring) und
        bleibt deshalb unveraendert, auch wenn Name/Betreff/Text bearbeitet
        werden."""
        template = self.templates_repo.get_by_key(key)
        if template is None:
            raise EntityNotFoundError(f"Mail-Vorlage '{key}' nicht gefunden")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(template, field, value)
        self.session.commit()
        self.session.refresh(template)
        return template

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

    def build(
        self,
        period: str,
        owner_user_ids: list[uuid.UUID] | None = None,
        shared_submission_ids: Collection[uuid.UUID] = (),
    ) -> dict[str, object]:
        """Cockpit/Analytics. Seit der Skalierung 3a rechnet die Datenbank: Zaehlungen und
        Summen per COUNT/SUM, Listen nur fuer die tatsaechlich angezeigten Zeilen
        (vorher wurden Prozesse, Angebote, Placements, Rechnungen und Aufgaben komplett
        als ORM-Objekte geladen und in Python gefiltert). Das Ergebnis ist unveraendert -
        tests/services/test_cockpit_equivalence.py vergleicht es mit der eingefrorenen
        frueheren Berechnung (tests/legacy_cockpit.py).

        Nutzerfilter (Analytics-Seite, Nutzer-Vorgabe "oben koennen mehrere user
        angewaehlt werden... standardauswahl sind alle user"): filtert nach
        Candidate.owner_user_id (gleiches Feld wie der "Meine Kandidaten"-
        Komfort-Filter), NICHT nach dem Ersteller von Submission/Offer/Placement/Fee,
        da diese Objekte kein eigenes owner_user_id-Feld mit derselben Bedeutung
        fuehren. `owner_user_ids=None` = kein Filter (alle Nutzer); eine leere Liste
        (alle Checkboxen abgewaehlt) filtert auf 0 Kandidaten statt auf "alle", damit
        die UI dem Auswahlzustand entspricht. `shared_submission_ids`: per Freigabe
        geteilte Prozesse zaehlen additiv zum Kandidaten-Filter."""
        now_aware = datetime.now(UTC)
        now = naive_utc(now_aware)
        days = {"week": 7, "month": 30, "quarter": 90}.get(period, 7)
        since_aware = now_aware - timedelta(days=days)
        since = naive_utc(since_aware)
        due_soon_aware = now_aware + timedelta(days=1)
        owner_filter_active = owner_user_ids is not None
        shared = list(shared_submission_ids)

        # --- Geltungsbereich als SQL-Bedingungen (None = keine Einschraenkung) ---
        candidate_scope = (
            select(Candidate.id).where(Candidate.owner_user_id.in_(owner_user_ids or []))
            if owner_filter_active
            else None
        )
        submission_scope = (
            or_(
                CandidateSubmission.candidate_id.in_(candidate_scope),
                CandidateSubmission.id.in_(shared),
            )
            if candidate_scope is not None
            else None
        )

        def in_scope(*conditions: Any) -> list[Any]:
            return [*conditions, *([submission_scope] if submission_scope is not None else [])]

        scoped_submission_ids = select(CandidateSubmission.id).where(*in_scope())

        # --- Prozesse ---
        period_submission_count = (
            self.session.scalar(
                select(func.count())
                .select_from(CandidateSubmission)
                .where(*in_scope(CandidateSubmission.created_at >= since_aware))
            )
            or 0
        )
        reached_interview_count = (
            self.session.scalar(
                select(func.count())
                .select_from(CandidateSubmission)
                .where(
                    *in_scope(
                        CandidateSubmission.created_at >= since_aware,
                        CandidateSubmission.status.in_(
                            [
                                SubmissionStatus.INTERVIEW,
                                SubmissionStatus.OFFER,
                                SubmissionStatus.PLACEMENT,
                            ]
                        ),
                    )
                )
            )
            or 0
        )
        expected = float(
            self.session.scalar(
                select(func.coalesce(func.sum(CandidateSubmission.expected_fee), 0)).where(
                    *in_scope()
                )
            )
            or 0
        )
        # Archivierte Placements ("Placement abschliessen", siehe
        # SubmissionService.archive()) verschwinden aus den beiden Action-Listen
        # (wie im Kanban), NICHT aus den KPI-Zahlen - die zaehlen sie weiter mit.
        hot_submissions = list(
            self.session.scalars(
                select(CandidateSubmission)
                .where(
                    *in_scope(
                        CandidateSubmission.status.in_(self.HOT),
                        CandidateSubmission.archived_at.is_(None),
                    )
                )
                .order_by(CandidateSubmission.created_at, CandidateSubmission.id)
            ).all()
        )
        # Prozesse im Status OFFER/PLACEMENT OHNE zugehoerigen Offer-/Placement-
        # Datensatz - unfertige Erfassungen (Kanban-Drag ohne ausgefuelltes
        # Formular), siehe CockpitRead.data_gaps. UEBER DEN GESAMTEN BESTAND
        # (nicht period-beschraenkt).
        has_offer = select(Offer.id).where(Offer.submission_id == CandidateSubmission.id).exists()
        has_placement = (
            select(Placement.id).where(Placement.submission_id == CandidateSubmission.id).exists()
        )
        gap_submissions = list(
            self.session.scalars(
                select(CandidateSubmission)
                .where(
                    *in_scope(
                        CandidateSubmission.archived_at.is_(None),
                        or_(
                            and_(CandidateSubmission.status == SubmissionStatus.OFFER, ~has_offer),
                            and_(
                                CandidateSubmission.status == SubmissionStatus.PLACEMENT,
                                ~has_placement,
                            ),
                        ),
                    )
                )
                .order_by(CandidateSubmission.created_at, CandidateSubmission.id)
            ).all()
        )

        # --- Angebote, Placements, Rechnungen ---
        offer_count = (
            self.session.scalar(
                select(func.count())
                .select_from(Offer)
                .where(
                    Offer.created_at >= since_aware,
                    *(
                        [Offer.submission_id.in_(scoped_submission_ids)]
                        if owner_filter_active
                        else []
                    ),
                )
            )
            or 0
        )
        placement_scope = (
            [Placement.submission_id.in_(scoped_submission_ids)] if owner_filter_active else []
        )
        placement_count = (
            self.session.scalar(
                select(func.count())
                .select_from(Placement)
                .where(Placement.created_at >= since_aware, *placement_scope)
            )
            or 0
        )
        # Rechnungen im Zeitraum (Fee kann neuer sein als sein Placement -
        # nachtraegliche Teilrechnung -, daher Zuordnung ueber ALLE Placements des
        # Geltungsbereichs, nicht nur die des Zeitraums).
        fee_scope = (
            [
                Fee.placement_id.in_(
                    select(Placement.id).where(Placement.submission_id.in_(scoped_submission_ids))
                )
            ]
            if owner_filter_active
            else []
        )
        paid_fees = self.session.execute(
            select(func.count(), func.coalesce(func.sum(Fee.amount_net), 0)).where(
                Fee.created_at >= since_aware,
                Fee.invoice_status == InvoiceStatus.PAID,
                *fee_scope,
            )
        ).one()
        paid = int(paid_fees[0] or 0)
        realized = float(paid_fees[1] or 0)
        # UEBER DEN GESAMTEN BESTAND (nicht auf `period` beschraenkt): eine seit
        # Monaten offene Rechnung bleibt "offen". Zaehlt DISTINCT Placements (nicht
        # Fees): ein Placement mit mehreren offenen Teilrechnungen zaehlt einmal.
        open_invoice_placement_count = (
            self.session.scalar(
                select(func.count(func.distinct(Fee.placement_id))).where(
                    Fee.invoice_status.not_in([InvoiceStatus.PAID, InvoiceStatus.CANCELLED]),
                    *fee_scope,
                )
            )
            or 0
        )

        # --- Aufgaben ---
        # Zurueckgestellte Tasks (POST /tasks/{id}/snooze) bleiben bis zum Ablauf der
        # Frist aus der To-Do-Sektion draussen - gleiche Regel wie bei
        # GET /tasks?status=open (repositories/tasks.py::filtered(exclude_snoozed=...)).
        task_conditions: list[Any] = [
            Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
            or_(Task.due_at.is_(None), Task.due_at <= due_soon_aware),
            or_(Task.snoozed_until.is_(None), Task.snoozed_until <= now_aware),
        ]
        if owner_filter_active and candidate_scope is not None:
            # Aufgaben gehoeren dem Nutzer, dem sie zugewiesen sind; ohne Zustaendigen
            # (z.B. automatisch aus Mails erzeugt) zaehlt der Owner des verknuepften
            # Kandidaten bzw. Prozesses - gleiche Regel wie bei den Prozessen oben.
            task_conditions.append(
                or_(
                    Task.owner_user_id.in_(owner_user_ids or []),
                    and_(Task.owner_user_id.is_(None), Task.candidate_id.in_(candidate_scope)),
                    and_(
                        Task.owner_user_id.is_(None),
                        Task.candidate_submission_id.in_(scoped_submission_ids),
                    ),
                )
            )
        due_tasks = list(
            self.session.scalars(
                select(Task).where(*task_conditions).order_by(Task.due_at, Task.id)
            ).all()
        )
        # Aeltere Task-Zeilen (vor Einfuehrung von candidate_id/client_company_id auf
        # automatischen Follow-ups) haben diese Spalten leer, obwohl die verknuepfte
        # Submission Kandidat/Kanzlei kennt - als Fallback ueber
        # candidate_submission_id aufloesen (nur Prozesse im Geltungsbereich).
        task_submission_ids = {
            task.candidate_submission_id for task in due_tasks if task.candidate_submission_id
        }
        submissions_by_id: dict[uuid.UUID, CandidateSubmission] = (
            {
                item.id: item
                for item in self.session.scalars(
                    select(CandidateSubmission).where(
                        *in_scope(CandidateSubmission.id.in_(task_submission_ids))
                    )
                ).all()
            }
            if task_submission_ids
            else {}
        )

        def _task_submission(task: Task) -> CandidateSubmission | None:
            if task.candidate_submission_id is None:
                return None
            return submissions_by_id.get(task.candidate_submission_id)

        def _task_candidate_id(task: Task) -> uuid.UUID | None:
            if task.candidate_id:
                return task.candidate_id
            submission = _task_submission(task)
            return submission.candidate_id if submission else None

        def _task_client_id(task: Task) -> uuid.UUID | None:
            if task.client_company_id:
                return task.client_company_id
            submission = _task_submission(task)
            return submission.client_company_id if submission else None

        task_candidate_ids = {task.id: _task_candidate_id(task) for task in due_tasks}
        task_client_ids = {task.id: _task_client_id(task) for task in due_tasks}

        # Namen fuer Kandidat/Kanzlei in einem Bulk-Query je Entitaet statt pro
        # Zeile nachzuladen: konstante statt mit der Datenmenge wachsende Query-Anzahl.
        candidate_ids = {value for value in task_candidate_ids.values() if value} | {
            item.candidate_id for item in hot_submissions
        } | {item.candidate_id for item in gap_submissions}
        client_ids = (
            {value for value in task_client_ids.values() if value}
            | {item.client_company_id for item in hot_submissions if item.client_company_id}
            | {item.client_company_id for item in gap_submissions if item.client_company_id}
        )
        candidate_names = self._candidate_names(candidate_ids)
        client_names = self._client_names(client_ids)

        def _task_names(task: Task) -> tuple[str | None, str | None]:
            candidate_id = task_candidate_ids[task.id]
            client_id = task_client_ids[task.id]
            candidate_name = candidate_names.get(candidate_id) if candidate_id else None
            client_name = client_names.get(client_id) if client_id else None
            return candidate_name, client_name

        important = []
        for task in due_tasks:
            candidate_name, client_name = _task_names(task)
            important.append(
                {
                    "kind": "task",
                    "title": task.title,
                    "detail": " — ".join(
                        filter(
                            None,
                            [candidate_name, client_name, task.description or "Offene Aufgabe"],
                        )
                    ),
                    "due_at": task.due_at,
                    "candidate_id": task_candidate_ids[task.id],
                    "client_company_id": task_client_ids[task.id],
                    "submission_id": task.candidate_submission_id,
                    "priority": task.priority.value,
                    "task_id": task.id,
                }
            )
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
        data_gaps = [
            {
                "kind": "submission",
                "title": self._hot_title(item, candidate_names, client_names),
                "detail": (
                    "Status 'Offer' ohne erfasstes Angebot (Gehalt/Fee fehlt)"
                    if item.status == SubmissionStatus.OFFER
                    else "Status 'Placement' ohne erfasstes Placement (Gehalt/Fee fehlt)"
                ),
                "due_at": item.follow_up_at,
                "candidate_id": item.candidate_id,
                "client_company_id": item.client_company_id,
                "submission_id": item.id,
                "priority": "normal",
            }
            for item in gap_submissions
        ]

        cv_count_query = select(func.count()).select_from(Candidate).where(
            Candidate.cv_in_recorded_at.isnot(None)
        )
        if candidate_scope is not None:
            cv_count_query = cv_count_query.where(Candidate.id.in_(candidate_scope))
        cv_count = self.session.scalar(cv_count_query) or 0

        sourcing = SourcingMetricService(self.session).totals_for_period(since.date(), now.date())
        # PITCH/INMAIL (Stufe 1 der 7-stufigen Pipeline, siehe CandidatePitchLog-
        # Docstring) - unabhaengig von SourcingMetric (Nutzer-Entscheidung "Ersetzen").
        pitch_query = (
            select(func.count())
            .select_from(CandidatePitchLog)
            .where(CandidatePitchLog.occurred_at >= since_aware)
        )
        if candidate_scope is not None:
            pitch_query = pitch_query.where(CandidatePitchLog.candidate_id.in_(candidate_scope))
        pitch_count = self.session.scalar(pitch_query) or 0

        # PIPELINE-Kennzahlen: aus der echten Statuswechsel-Historie (AuditLog), nicht
        # aus Anlagezeitpunkt oder aktuellem Status - siehe services/recruiting.py::
        # stage_reached_counts. Ueber ALLE Prozesse des Geltungsbereichs (eine im Zeitraum
        # erreichte Stufe setzt nicht voraus, dass der Prozess selbst im Zeitraum
        # angelegt wurde).
        reached_since = stage_reached_counts(self.session, scoped_submission_ids, since=since)
        return {
            "period": period,
            "important": important,
            "hot_processes": hot,
            "data_gaps": data_gaps,
            "sourcing": sourcing,
            "recruiting_kpis": self._recruiting_kpis(),
            "kpis": {
                "qualification_calls": period_submission_count,
                "cv_available": cv_count,
                "submissions": period_submission_count,
                "cv_outs_reached_count": len(reached_since[SubmissionStatus.CV_OUT]),
                "interviews": len(reached_since[SubmissionStatus.INTERVIEW]),
                "offers": offer_count,
                "offer_stage_reached_count": len(reached_since[SubmissionStatus.OFFER]),
                "placements": placement_count,
                "placement_stage_reached_count": len(reached_since[SubmissionStatus.PLACEMENT]),
                "expected_fees": expected,
                "realized_fees": realized,
                "open_invoice_placement_count": open_invoice_placement_count,
                "pitches": pitch_count,
            },
            "rates": {
                "pitch_to_qualification_call_rate": self._rate(
                    period_submission_count, pitch_count
                ),
                "submission_to_interview": self._rate(
                    reached_interview_count, period_submission_count
                ),
                "interview_to_offer": self._rate(offer_count, reached_interview_count),
                "offer_to_placement": self._rate(placement_count, offer_count),
                "placement_to_paid": self._rate(paid, placement_count),
            },
        }

    def _recruiting_kpis(self) -> dict[str, float | None]:
        """Etablierte Standard-Recruiting-Kennzahlen ueber den GESAMTEN
        historischen Bestand (nicht auf den period-Zeitraum beschraenkt - ein
        Median ueber nur eine Woche/einen Monat haette zu wenige Datenpunkte, um
        aussagekraeftig zu sein). Nur die benoetigten Spalten werden geladen (keine
        ORM-Objekte), der Median/Mittelwert bleibt in Python (portabel fuer SQLite)."""
        fill_days = [
            (naive_utc(placement_created) - naive_utc(submission_created)).days
            for placement_created, submission_created in self.session.execute(
                select(Placement.created_at, CandidateSubmission.created_at).join(
                    CandidateSubmission, CandidateSubmission.id == Placement.submission_id
                )
            ).all()
        ]

        # Time-to-Interview: Submission-Erstellung bis zum Activity-Eintrag, der den
        # Uebergang IN "interview" protokolliert (siehe services/submissions.py::
        # transition(), Activity.details ist immer "{alter_status} -> {neuer_status}"
        # mit optionalem ": {grund}"-Suffix nur bei Abbruch/Storno-Transitionen).
        interview_days = [
            (naive_utc(occurred_at) - naive_utc(submission_created)).days
            for occurred_at, submission_created in self.session.execute(
                select(Activity.occurred_at, CandidateSubmission.created_at)
                .join(
                    CandidateSubmission,
                    CandidateSubmission.id == Activity.candidate_submission_id,
                )
                .where(
                    Activity.activity_type == "submission_status_changed",
                    Activity.details.like("%-> interview"),
                )
            ).all()
        ]

        fees = [
            float(value)
            for value in self.session.scalars(select(Placement.calculated_fee)).all()
        ]

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
