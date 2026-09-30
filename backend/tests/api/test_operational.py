import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.email_template import EmailTemplate
from cc_crm.models.enums import InvoiceStatus
from cc_crm.models.recruiting import Fee
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.task import Task
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService


@pytest.fixture
def second_user_token(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        session.add(User(email="colleague@commandeur.example", hashed_password=hash_password("x")))
        session.commit()
        _, token = AuthService(session).login("colleague@commandeur.example", "x")
        return token


@pytest.fixture
def admin_token(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        session.add(
            User(
                email="chef@commandeur.example", hashed_password=hash_password("x"), role="admin"
            )
        )
        session.commit()
        _, token = AuthService(session).login("chef@commandeur.example", "x")
        return token


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_cockpit_and_email_templates(client: TestClient) -> None:
    cockpit_response = client.get("/api/v1/cockpit?period=week")
    assert cockpit_response.status_code == 200
    cockpit = cockpit_response.json()
    assert cockpit["period"] == "week"
    assert cockpit["kpis"]["submissions"] == 0
    assert "submission_to_interview" in cockpit["rates"]
    assert "pitches" in cockpit["kpis"]
    assert "pitch_to_qualification_call_rate" in cockpit["rates"]


class TestCockpitOwnerFilter:
    """Neuer Nutzerfilter oben in der Analytics-Seite (Nutzer-Vorgabe:
    "standardauswahl sind alle user... Mehrfachauswahl moeglich") - filtert
    nach Candidate.owner_user_id, siehe CockpitService.build."""

    @staticmethod
    def _two_owners_with_one_submission_each(client: TestClient, second_user_token: str) -> None:
        client.post("/api/v1/candidates", json={"first_name": "Mine", "last_name": "A"})
        client.post(
            "/api/v1/candidates",
            json={"first_name": "Colleague", "last_name": "B"},
            headers=auth_header(second_user_token),
        )
        client.post("/api/v1/submissions", json={"candidate_id": _candidate_id(client, "A")})
        client.post(
            "/api/v1/submissions",
            json={"candidate_id": _candidate_id(client, "B")},
            headers=auth_header(second_user_token),
        )

    def test_admin_without_filter_sees_all_owners(
        self, client: TestClient, second_user_token: str, admin_token: str
    ) -> None:
        self._two_owners_with_one_submission_each(client, second_user_token)

        cockpit = client.get(
            "/api/v1/cockpit?period=week", headers=auth_header(admin_token)
        ).json()
        assert cockpit["kpis"]["submissions"] == 2

    def test_non_admin_without_filter_sees_only_own_data(
        self, client: TestClient, second_user_token: str
    ) -> None:
        self._two_owners_with_one_submission_each(client, second_user_token)

        mine = client.get("/api/v1/cockpit?period=week").json()
        theirs = client.get(
            "/api/v1/cockpit?period=week", headers=auth_header(second_user_token)
        ).json()
        # "Heisse Prozesse" wird aus derselben (hier gefilterten) Prozessliste
        # gebildet wie kpis.submissions.
        assert mine["kpis"]["submissions"] == 1
        assert theirs["kpis"]["submissions"] == 1

    def test_non_admin_without_filter_sees_only_own_tasks(
        self,
        client: TestClient,
        second_user_token: str,
        session_factory: sessionmaker[Session],
    ) -> None:
        me = client.get("/api/v1/auth/me").json()
        colleague = client.get("/api/v1/auth/me", headers=auth_header(second_user_token)).json()
        mine_candidate = client.post(
            "/api/v1/candidates", json={"first_name": "Mine", "last_name": "A"}
        ).json()
        with session_factory() as session:
            session.add_all(
                [
                    Task(title="Meine Aufgabe", owner_user_id=uuid.UUID(me["id"])),
                    Task(title="Fremde Aufgabe", owner_user_id=uuid.UUID(colleague["id"])),
                    # Ohne Zustaendigen, aber an meinem Kandidaten -> meine.
                    Task(title="Mail-Aufgabe", candidate_id=uuid.UUID(mine_candidate["id"])),
                    # Ohne Zustaendigen und ohne Bezug -> niemandes.
                    Task(title="Verwaiste Aufgabe"),
                ]
            )
            session.commit()

        mine = client.get("/api/v1/cockpit?period=week").json()
        assert sorted(item["title"] for item in mine["important"] if item["kind"] == "task") == [
            "Mail-Aufgabe",
            "Meine Aufgabe",
        ]

    def test_filter_restricts_to_selected_owners(
        self, client: TestClient, second_user_token: str
    ) -> None:
        me = client.get("/api/v1/auth/me").json()
        client.post("/api/v1/candidates", json={"first_name": "Mine", "last_name": "A"})
        client.post(
            "/api/v1/candidates",
            json={"first_name": "Colleague", "last_name": "B"},
            headers=auth_header(second_user_token),
        )
        client.post("/api/v1/submissions", json={"candidate_id": _candidate_id(client, "A")})
        client.post(
            "/api/v1/submissions",
            json={"candidate_id": _candidate_id(client, "B")},
            headers=auth_header(second_user_token),
        )

        cockpit = client.get(f"/api/v1/cockpit?period=week&owner_user_id={me['id']}").json()
        assert cockpit["kpis"]["submissions"] == 1

    def test_multiple_owner_ids_are_unioned(
        self, client: TestClient, second_user_token: str
    ) -> None:
        me = client.get("/api/v1/auth/me").json()
        colleague = client.get("/api/v1/auth/me", headers=auth_header(second_user_token)).json()
        client.post("/api/v1/candidates", json={"first_name": "Mine", "last_name": "A"})
        client.post(
            "/api/v1/candidates",
            json={"first_name": "Colleague", "last_name": "B"},
            headers=auth_header(second_user_token),
        )
        client.post("/api/v1/submissions", json={"candidate_id": _candidate_id(client, "A")})
        client.post(
            "/api/v1/submissions",
            json={"candidate_id": _candidate_id(client, "B")},
            headers=auth_header(second_user_token),
        )

        cockpit = client.get(
            f"/api/v1/cockpit?period=week&owner_user_id={me['id']}&owner_user_id={colleague['id']}"
        ).json()
        assert cockpit["kpis"]["submissions"] == 2


def _candidate_id(client: TestClient, last_name: str) -> str:
    candidates = client.get("/api/v1/candidates").json()["items"]
    return next(item["id"] for item in candidates if item["last_name"] == last_name)


class TestCockpitPitches:
    """Pitch/InMail (Stufe 1 der 7-stufigen Pipeline) - ersetzt die vorherige
    manuelle SourcingFunnel.pitches-Zahl (Nutzer-Entscheidung "Ersetzen")."""

    def test_pitches_counted_in_period(self, client: TestClient) -> None:
        candidate = client.post(
            "/api/v1/candidates", json={"first_name": "Pitch", "last_name": "Cockpit"}
        ).json()
        client.post(
            f"/api/v1/candidates/{candidate['id']}/pitch-log",
            json={"occurred_at": datetime.now(UTC).isoformat()},
        )
        client.post(
            f"/api/v1/candidates/{candidate['id']}/pitch-log",
            json={"occurred_at": datetime.now(UTC).isoformat()},
        )

        cockpit = client.get("/api/v1/cockpit?period=week").json()
        assert cockpit["kpis"]["pitches"] == 2

    def test_pitches_outside_period_are_excluded(self, client: TestClient) -> None:
        candidate = client.post(
            "/api/v1/candidates", json={"first_name": "OldPitch", "last_name": "Cockpit"}
        ).json()
        old = datetime.now(UTC) - timedelta(days=60)
        client.post(
            f"/api/v1/candidates/{candidate['id']}/pitch-log",
            json={"occurred_at": old.isoformat()},
        )

        cockpit = client.get("/api/v1/cockpit?period=week").json()
        assert cockpit["kpis"]["pitches"] == 0

    def test_pitches_respect_owner_filter(
        self, client: TestClient, second_user_token: str
    ) -> None:
        me = client.get("/api/v1/auth/me").json()
        my_candidate = client.post(
            "/api/v1/candidates", json={"first_name": "Mine", "last_name": "Pitch"}
        ).json()
        colleague_candidate = client.post(
            "/api/v1/candidates",
            json={"first_name": "Colleague", "last_name": "Pitch"},
            headers=auth_header(second_user_token),
        ).json()

        client.post(
            f"/api/v1/candidates/{my_candidate['id']}/pitch-log",
            json={"occurred_at": datetime.now(UTC).isoformat()},
        )
        client.post(
            f"/api/v1/candidates/{colleague_candidate['id']}/pitch-log",
            json={"occurred_at": datetime.now(UTC).isoformat()},
        )

        cockpit = client.get(f"/api/v1/cockpit?period=week&owner_user_id={me['id']}").json()
        assert cockpit["kpis"]["pitches"] == 1


def _walk_submission_to_placement(client: TestClient) -> dict:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Anna", "last_name": "Muster"}
    ).json()
    company = client.post(
        "/api/v1/clients", json={"name": "Muster Kanzlei", "status": "active"}
    ).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    for target_status in ("cv_in", "cv_out", "interview", "offer", "placement"):
        response = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition",
            json={"status": target_status},
        )
        assert response.status_code == 200, response.text
    placement = client.post(
        f"/api/v1/submissions/{submission['id']}/placement",
        json={
            "start_date": "2026-09-01",
            "final_salary": "70000.00",
            "fee_percentage": "27.00",
            "guarantee_period_months": 6,
        },
    )
    assert placement.status_code == 201, placement.text
    return placement.json()


class TestCockpitOpenInvoiceCount:
    """kpis.open_invoice_placement_count - ersetzt den frueher hartcodierten
    Platzhaltertext "1 Placement hat offenen Rechnungsstatus." im Cockpit
    (Nutzer-Feedback "Prozesse abschliessen...", Punkt 1)."""

    def test_zero_when_no_fees_exist(self, client: TestClient) -> None:
        cockpit = client.get("/api/v1/cockpit?period=week").json()
        assert cockpit["kpis"]["open_invoice_placement_count"] == 0

    def test_counts_placement_with_an_unpaid_fee(self, client: TestClient) -> None:
        placement = _walk_submission_to_placement(client)
        fee = client.post(
            f"/api/v1/placements/{placement['id']}/fees", json={"amount_net": "18900.00"}
        )
        assert fee.status_code == 201, fee.text
        assert fee.json()["invoice_status"] == "draft"

        cockpit = client.get("/api/v1/cockpit?period=week").json()

        assert cockpit["kpis"]["open_invoice_placement_count"] == 1

    def test_does_not_count_a_paid_fee(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        # Kein PATCH-Endpunkt fuer invoice_status vorhanden - Rechnungsstatus
        # wird bisher nur intern/administrativ gepflegt, direkt in der DB
        # nachgestellt.
        placement = _walk_submission_to_placement(client)
        fee = client.post(
            f"/api/v1/placements/{placement['id']}/fees", json={"amount_net": "18900.00"}
        ).json()
        with session_factory() as session:
            db_fee = session.get(Fee, uuid.UUID(fee["id"]))
            assert db_fee is not None
            db_fee.invoice_status = InvoiceStatus.PAID
            session.commit()

        cockpit = client.get("/api/v1/cockpit?period=week").json()

        assert cockpit["kpis"]["open_invoice_placement_count"] == 0

    def test_ignores_period_scope(self, client: TestClient) -> None:
        """Anders als die period-gescopten Kennzahlen: eine offene Rechnung
        bleibt offen, egal welchen Cockpit-Zeitraum man gerade ansieht."""
        placement = _walk_submission_to_placement(client)
        client.post(f"/api/v1/placements/{placement['id']}/fees", json={"amount_net": "1.00"})

        for period in ("week", "month", "quarter"):
            cockpit = client.get(f"/api/v1/cockpit?period={period}").json()
            assert cockpit["kpis"]["open_invoice_placement_count"] == 1


class TestCockpitPipelineKpis:
    """Pipeline-Kennzahlen (Nutzer-Entscheidung "KPIs stimmen nicht", Punkt
    3): aus der echten Statuswechsel-Historie (AuditLog), nicht aus
    Anlagezeitpunkt oder Kindobjekten - siehe services/operational.py::
    CockpitService.build."""

    def test_cv_outs_reached_counts_transition_not_creation(self, client: TestClient) -> None:
        candidate = client.post(
            "/api/v1/candidates", json={"first_name": "Anna", "last_name": "Muster"}
        ).json()
        company = client.post(
            "/api/v1/clients", json={"name": "Kanzlei CvOut", "status": "active"}
        ).json()
        submission = client.post(
            "/api/v1/submissions",
            json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
        ).json()
        for target in ("cv_in", "cv_out"):
            response = client.patch(
                f"/api/v1/submissions/{submission['id']}/transition", json={"status": target}
            )
            assert response.status_code == 200, response.text

        cockpit = client.get("/api/v1/cockpit?period=week").json()

        assert cockpit["kpis"]["cv_outs_reached_count"] == 1
        # "submissions" (Neue Prozesse) bleibt unabhaengig davon 1, da genau
        # eine Submission im Zeitraum angelegt wurde - beide Zahlen duerfen
        # sich unterscheiden, das ist keine Inkonsistenz.
        assert cockpit["kpis"]["submissions"] == 1

    def test_interviews_respects_period_like_offers_and_placements(
        self, client: TestClient
    ) -> None:
        candidate = client.post(
            "/api/v1/candidates", json={"first_name": "Anna", "last_name": "Muster"}
        ).json()
        company = client.post(
            "/api/v1/clients", json={"name": "Kanzlei Interview", "status": "active"}
        ).json()
        submission = client.post(
            "/api/v1/submissions",
            json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
        ).json()
        for target in ("cv_in", "cv_out", "interview"):
            response = client.patch(
                f"/api/v1/submissions/{submission['id']}/transition", json={"status": target}
            )
            assert response.status_code == 200, response.text

        cockpit = client.get("/api/v1/cockpit?period=week").json()

        assert cockpit["kpis"]["interviews"] == 1

    def test_offer_and_placement_stage_reached_count_via_transition_alone(
        self, client: TestClient
    ) -> None:
        """Reiner Kanban-Drag auf 'placement', OHNE das Placement-Formular
        auszufuellen - die Pipeline-Kennzahl zaehlt trotzdem den erreichten
        Status; die kaufmaennische Kennzahl (placements) bleibt 0, da kein
        Placement-Datensatz existiert."""
        candidate = client.post(
            "/api/v1/candidates", json={"first_name": "Anna", "last_name": "Muster"}
        ).json()
        company = client.post(
            "/api/v1/clients", json={"name": "Kanzlei Placement", "status": "active"}
        ).json()
        submission = client.post(
            "/api/v1/submissions",
            json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
        ).json()
        for target in ("cv_in", "cv_out", "interview", "offer", "placement"):
            response = client.patch(
                f"/api/v1/submissions/{submission['id']}/transition", json={"status": target}
            )
            assert response.status_code == 200, response.text

        cockpit = client.get("/api/v1/cockpit?period=week").json()

        assert cockpit["kpis"]["placement_stage_reached_count"] == 1
        assert cockpit["kpis"]["placements"] == 0
        assert cockpit["kpis"]["offer_stage_reached_count"] == 1


class TestCockpitDataGaps:
    """data_gaps: Prozesse im Status OFFER/PLACEMENT ohne zugehoerigen
    Offer-/Placement-Datensatz - sichtbar machen statt stillschweigend
    hinnehmen (Nutzer-Entscheidung Punkt 3d)."""

    def test_placement_without_record_appears_in_data_gaps(self, client: TestClient) -> None:
        candidate = client.post(
            "/api/v1/candidates", json={"first_name": "Anna", "last_name": "Muster"}
        ).json()
        company = client.post(
            "/api/v1/clients", json={"name": "Kanzlei Gap", "status": "active"}
        ).json()
        submission = client.post(
            "/api/v1/submissions",
            json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
        ).json()
        for target in ("cv_in", "cv_out", "interview", "offer", "placement"):
            client.patch(
                f"/api/v1/submissions/{submission['id']}/transition", json={"status": target}
            )

        cockpit = client.get("/api/v1/cockpit?period=week").json()

        gap_submission_ids = {gap["submission_id"] for gap in cockpit["data_gaps"]}
        assert submission["id"] in gap_submission_ids

    def test_placement_with_record_does_not_appear_in_data_gaps(
        self, client: TestClient
    ) -> None:
        placement = _walk_submission_to_placement(client)

        cockpit = client.get("/api/v1/cockpit?period=week").json()

        gap_submission_ids = {gap["submission_id"] for gap in cockpit["data_gaps"]}
        assert placement["submission_id"] not in gap_submission_ids

    def test_no_gaps_when_everything_is_properly_recorded(self, client: TestClient) -> None:
        cockpit = client.get("/api/v1/cockpit?period=week").json()
        assert cockpit["data_gaps"] == []


def test_email_templates_have_distinct_specific_bodies(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Regressionsschutz: templates() lieferte frueher fuer JEDEN Key
    denselben generischen body-Text - nur der subject unterschied sich.

    Vorlagen liegen seit "Mailvorlagen editierbar machen" in der Tabelle
    email_templates statt hartcodiert in EmailWorkflowService.TEMPLATES - der
    `client`-Fixture baut die Test-DB per `Base.metadata.create_all()` auf
    (keine Alembic-Migration, siehe conftest.py), deshalb werden die fuer
    diesen Regressionstest relevanten Vorlagen hier direkt per ORM geseedet
    (der eigentliche Seed-Migrationsinhalt hat seinen eigenen Test, siehe
    tests/test_email_templates_seed_migration.py)."""
    with session_factory() as session:
        session.add_all(
            [
                EmailTemplate(
                    key="post_qualification_call",
                    name="Nach Quali Call",
                    subject="Vielen Dank für das Gespräch, {candidate}",
                    body="Guten Tag {candidate},\n\nNächster Schritt: {next_step}\n\nBeste Grüße",
                ),
                EmailTemplate(
                    key="candidate_submission",
                    name="CV-Out Vorstellung",
                    subject="Profilvorstellung: {candidate} – {role}",
                    body=(
                        "{short_profile}\n\nGehaltsvorstellung: {salary}\n"
                        "Kündigungsfrist: {notice_period}"
                    ),
                ),
                EmailTemplate(
                    key="interview_confirmation",
                    name="Interview bestätigen",
                    subject="Interviewtermin bei {client}",
                    body="Guten Tag {contact},\n\nInterviewtermin für {candidate} bei {client}.",
                ),
                EmailTemplate(
                    key="interview_feedback",
                    name="Interviewfeedback nachfassen (Kanzlei)",
                    subject="Kurzes Feedback zum Interview mit {candidate}",
                    body="Guten Tag {contact},\n\nWie war Ihr Eindruck von {candidate}?",
                ),
                EmailTemplate(
                    key="interview_feedback_candidate",
                    name="Interviewfeedback nachfassen (Kandidat)",
                    subject="Rückmeldung zu Ihrem Interview bei {client}",
                    body="Guten Tag {candidate},\n\nNächster Schritt: {next_step}",
                ),
            ]
        )
        session.commit()

    templates = client.get("/api/v1/email-templates").json()
    by_key = {item["key"]: item for item in templates}

    expected_keys = {
        "post_qualification_call",
        "candidate_submission",
        "interview_confirmation",
        "interview_feedback",
        "interview_feedback_candidate",
    }
    assert expected_keys.issubset(by_key.keys())

    bodies = [item["body"] for item in templates]
    assert len(bodies) == len(set(bodies)), "jede Vorlage muss einen eigenen body-Text haben"

    post_qc = by_key["post_qualification_call"]
    assert post_qc["subject"] == "Vielen Dank für das Gespräch, {candidate}"
    assert "{next_step}" in post_qc["body"]
    assert "{candidate}" in post_qc["body"]

    submission = by_key["candidate_submission"]
    assert submission["subject"] == "Profilvorstellung: {candidate} – {role}"
    assert "{short_profile}" in submission["body"]
    assert "{salary}" in submission["body"]
    assert "{notice_period}" in submission["body"]

    interview_confirmation = by_key["interview_confirmation"]
    assert interview_confirmation["subject"] == "Interviewtermin bei {client}"

    interview_feedback = by_key["interview_feedback"]
    assert interview_feedback["subject"] == "Kurzes Feedback zum Interview mit {candidate}"

    interview_feedback_candidate = by_key["interview_feedback_candidate"]
    assert interview_feedback_candidate["subject"] == "Rückmeldung zu Ihrem Interview bei {client}"
    assert "{next_step}" in interview_feedback_candidate["body"]


def test_cockpit_hot_processes_and_important_include_candidate_and_client_names(
    client: TestClient,
) -> None:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Max", "last_name": "Mustermann"}
    ).json()
    company = client.post("/api/v1/clients", json={"name": "ACME GmbH"}).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    for target in ["cv_in", "cv_out", "interview"]:
        response = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition", json={"status": target}
        )
        assert response.status_code == 200, response.text

    cockpit = client.get("/api/v1/cockpit?period=week").json()
    hot_titles = [item["title"] for item in cockpit["hot_processes"]]
    assert any("Max Mustermann" in title and "ACME GmbH" in title for title in hot_titles)

    important_details = [item["detail"] for item in cockpit["important"]]
    assert any("Max Mustermann" in detail for detail in important_details)


def test_cockpit_important_task_items_carry_task_id_for_dashboard_actions(
    client: TestClient,
) -> None:
    """Die Dashboard-To-Do-Sektion (snooze/resolve) braucht die Task-ID in
    jedem "important"-Eintrag vom kind="task"."""
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Erika", "last_name": "Musterfrau"}
    ).json()
    task = client.post(
        "/api/v1/tasks",
        json={"candidate_id": candidate["id"], "title": "LinkedIn-Antwort: Erika Musterfrau"},
    ).json()

    cockpit = client.get("/api/v1/cockpit?period=week").json()
    matching = [item for item in cockpit["important"] if item.get("task_id") == task["id"]]
    assert len(matching) == 1
    assert matching[0]["kind"] == "task"
    assert matching[0]["candidate_id"] == candidate["id"]


def test_cockpit_important_excludes_snoozed_tasks(client: TestClient) -> None:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Zurueck", "last_name": "Gestellt"}
    ).json()
    task = client.post(
        "/api/v1/tasks",
        json={"candidate_id": candidate["id"], "title": "LinkedIn-Antwort: Zurueck Gestellt"},
    ).json()

    before = client.get("/api/v1/cockpit?period=week").json()
    assert any(item.get("task_id") == task["id"] for item in before["important"])

    client.post(f"/api/v1/tasks/{task['id']}/snooze", json={"days": 3})

    after = client.get("/api/v1/cockpit?period=week").json()
    assert not any(item.get("task_id") == task["id"] for item in after["important"])


def test_cockpit_important_resolves_names_via_submission_when_task_fields_are_null(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Aeltere Task-Zeilen (vor Einfuehrung von candidate_id/client_company_id
    auf automatischen Follow-ups) haben diese Spalten leer, obwohl die
    verknuepfte Submission Kandidat/Kanzlei kennt - die Uebersicht muss den
    Namen trotzdem ueber candidate_submission_id auflösen, statt einen
    namenlosen Eintrag zu zeigen (siehe services/operational.py::build)."""
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Erika", "last_name": "Beispiel"}
    ).json()
    company = client.post("/api/v1/clients", json={"name": "Beispiel Steuerberatung"}).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()

    with session_factory() as session:
        session.add(
            Task(
                candidate_id=None,
                client_company_id=None,
                candidate_submission_id=uuid.UUID(submission["id"]),
                title="Interviewfeedback nachfassen",
                description="Automatisch aus dem Prozessstatus erzeugtes Follow-up",
                due_at=datetime.now(UTC),
            )
        )
        session.commit()

    cockpit = client.get("/api/v1/cockpit?period=week").json()
    important_details = [item["detail"] for item in cockpit["important"]]
    assert any(
        "Erika Beispiel" in detail and "Beispiel Steuerberatung" in detail
        for detail in important_details
    )


def test_cockpit_sourcing_funnel_has_no_data_until_a_metric_is_recorded(
    client: TestClient,
) -> None:
    empty = client.get("/api/v1/cockpit?period=week").json()
    assert empty["sourcing"]["has_data"] is False
    assert empty["sourcing"]["pitches"] == 0
    assert empty["sourcing"]["pitch_to_response_rate"] is None

    today = datetime.now(UTC).date()
    metric = client.post(
        "/api/v1/sourcing-metrics",
        json={
            "period_start": str(today - timedelta(days=1)),
            "period_end": str(today),
            "source": "LinkedIn",
            "pitches": 40,
            "responses": 10,
            "positive_responses": 4,
            "qualification_calls": 3,
        },
    )
    assert metric.status_code == 201

    filled = client.get("/api/v1/cockpit?period=week").json()
    assert filled["sourcing"]["has_data"] is True
    assert filled["sourcing"]["pitches"] == 40
    assert filled["sourcing"]["responses"] == 10
    assert filled["sourcing"]["pitch_to_response_rate"] == 25.0
    assert filled["sourcing"]["response_to_qualification_call_rate"] == 30.0


def test_profile_suggestion_is_an_editable_draft(client: TestClient) -> None:
    candidate_response = client.post(
        "/api/v1/candidates",
        json={
            "candidate_number": "1001",
            "first_name": "Erika",
            "last_name": "Muster",
            "job_title": "Steuerberaterin",
            "qualification": "Steuerberaterexamen",
            "city": "Stuttgart",
            "cv_available": True,
        },
    )
    candidate_id = candidate_response.json()["id"]

    response = client.post(f"/api/v1/candidates/{candidate_id}/profile-suggestion")
    assert response.status_code == 200
    suggestion = response.json()
    assert suggestion["is_draft"] is True
    assert "Steuerberaterin" in suggestion["text"]


def test_activities_and_tasks_filter_by_candidate_id(client: TestClient) -> None:
    candidate_a = client.post(
        "/api/v1/candidates", json={"first_name": "Anna", "last_name": "A"}
    ).json()
    candidate_b = client.post(
        "/api/v1/candidates", json={"first_name": "Bea", "last_name": "B"}
    ).json()
    client.post(
        "/api/v1/activities",
        json={
            "candidate_id": candidate_a["id"],
            "activity_type": "note",
            "subject": "Anruf mit Anna",
            "occurred_at": "2026-06-01T10:00:00Z",
        },
    )
    client.post(
        "/api/v1/activities",
        json={
            "candidate_id": candidate_b["id"],
            "activity_type": "note",
            "subject": "Anruf mit Bea",
            "occurred_at": "2026-06-01T10:00:00Z",
        },
    )
    client.post(
        "/api/v1/tasks",
        json={"candidate_id": candidate_a["id"], "title": "Follow-up Anna"},
    )
    client.post(
        "/api/v1/tasks",
        json={"candidate_id": candidate_b["id"], "title": "Follow-up Bea"},
    )

    activities = client.get(f"/api/v1/activities?candidate_id={candidate_a['id']}").json()
    assert len(activities) == 1
    assert activities[0]["subject"] == "Anruf mit Anna"

    tasks = client.get(f"/api/v1/tasks?candidate_id={candidate_a['id']}").json()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Follow-up Anna"


def test_document_generic_filename_flag_is_computed_on_create(client: TestClient) -> None:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Generic", "last_name": "Filename"}
    ).json()
    generic = client.post(
        "/api/v1/documents",
        json={
            "owner_type": "candidate",
            "owner_id": candidate["id"],
            "document_type": "cv",
            "filename": "Lebenslauf (2).pdf",
            "storage_key": "candidates/generic.pdf",
        },
    )
    assert generic.status_code == 201, generic.text
    assert generic.json()["has_generic_filename"] is True

    specific = client.post(
        "/api/v1/documents",
        json={
            "owner_type": "candidate",
            "owner_id": candidate["id"],
            "document_type": "cv",
            "filename": "lebenslauf-hans-mueller.pdf",
            "storage_key": "candidates/specific.pdf",
        },
    )
    assert specific.status_code == 201, specific.text
    assert specific.json()["has_generic_filename"] is False


def test_documents_filter_by_owner(client: TestClient) -> None:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Doc", "last_name": "Owner"}
    ).json()
    client.post(
        "/api/v1/documents",
        json={
            "owner_type": "candidate",
            "owner_id": candidate["id"],
            "document_type": "cv",
            "filename": "cv.pdf",
            "storage_key": "candidates/cv.pdf",
        },
    )
    client.post(
        "/api/v1/documents",
        json={
            "owner_type": "client",
            "owner_id": candidate["id"],
            "document_type": "terms",
            "filename": "agb.pdf",
            "storage_key": "clients/agb.pdf",
        },
    )

    documents = client.get(
        f"/api/v1/documents?owner_type=candidate&owner_id={candidate['id']}"
    ).json()
    assert len(documents) == 1
    assert documents[0]["filename"] == "cv.pdf"


def test_recruiting_kpis_are_null_until_data_exists(client: TestClient) -> None:
    cockpit = client.get("/api/v1/cockpit?period=month").json()
    kpis = cockpit["recruiting_kpis"]
    assert kpis["time_to_fill_days"] is None
    assert kpis["time_to_interview_days"] is None
    assert kpis["average_fee_per_placement"] is None


def test_recruiting_kpis_time_to_fill_time_to_interview_and_average_fee(
    client: TestClient, session_factory
) -> None:
    """time_to_fill_days/time_to_interview_days/average_fee_per_placement
    laufen ueber den GESAMTEN historischen Bestand (nicht period-begrenzt) -
    siehe CockpitService._recruiting_kpis. Backdatiert submission.created_at
    direkt in der DB, um einen deterministischen Tage-Delta zu erzwingen
    (created_at ist server-seitig gesetzt, ueber die API nicht steuerbar)."""
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "KPI", "last_name": "Test"}
    ).json()
    company = client.post("/api/v1/clients", json={"name": "Kanzlei KPI"}).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    for status in ("cv_in", "cv_out", "interview", "offer", "placement"):
        response = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition", json={"status": status}
        )
        assert response.status_code == 200, response.text

    placement = client.post(
        f"/api/v1/submissions/{submission['id']}/placement",
        json={"start_date": "2026-09-01", "final_salary": "60000.00", "fee_percentage": "25.00"},
    ).json()

    with session_factory() as session:
        db_submission = session.get(CandidateSubmission, uuid.UUID(submission["id"]))
        assert db_submission is not None
        db_submission.created_at = datetime.now(UTC) - timedelta(days=12)
        session.commit()

    cockpit = client.get("/api/v1/cockpit?period=month").json()
    kpis = cockpit["recruiting_kpis"]
    assert kpis["time_to_fill_days"] is not None
    assert 11 <= kpis["time_to_fill_days"] <= 13
    assert kpis["time_to_interview_days"] is not None
    assert 11 <= kpis["time_to_interview_days"] <= 13
    assert kpis["average_fee_per_placement"] == float(placement["calculated_fee"])
