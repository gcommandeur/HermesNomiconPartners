"""Tests fuer die editierbaren Mail-Vorlagen (Auftrag "Mailvorlagen editierbar
machen"): GET liest aus der DB, Platzhalter werden dynamisch pro Vorlage per
Regex extrahiert, PATCH aendert nur name/subject/body - `key` bleibt stabil,
da MailingGroup.template_key ihn referenziert (siehe models/email_template.py).

Der `client`-Fixture baut die Test-DB per `Base.metadata.create_all()` auf
(keine Migrationen, siehe conftest.py) - die Vorlagen-Zeilen fuer diese Tests
werden deshalb direkt per ORM gesetzt, nicht ueber die Seed-Migration (die hat
ihren eigenen Test, siehe test_email_templates_seed_migration.py)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.email_template import EmailTemplate
from cc_crm.services.operational import EmailWorkflowService


@pytest.fixture
def seeded_template(session_factory: sessionmaker[Session]) -> EmailTemplate:
    with session_factory() as session:
        template = EmailTemplate(
            key="submission_follow_up",
            name="CV-Out nachfassen",
            subject="Feedback zu {candidate}",
            body="Guten Tag {contact},\n\nFeedback zu {candidate}?\n\nBeste Grüße",
        )
        session.add(template)
        session.commit()
        session.refresh(template)
        return template


def test_extract_placeholders_returns_only_tokens_used_in_this_template() -> None:
    placeholders = EmailWorkflowService.extract_placeholders(
        subject="Vorlage für {candidate}",
        body="Sehr geehrte(r) {contact},\n\n{candidate} - {role} - {candidate}\n\nGrüße",
    )
    # dedupliziert, Reihenfolge des ersten Vorkommens, keine Platzhalter, die
    # gar nicht im Text stehen (z.B. "salary" fehlt hier bewusst).
    assert placeholders == ["candidate", "contact", "role"]


def test_extract_placeholders_empty_when_template_has_no_tokens() -> None:
    assert EmailWorkflowService.extract_placeholders("Kein Platzhalter", "Auch hier keiner.") == []


def test_get_email_templates_returns_dynamic_per_template_placeholders(
    client: TestClient, seeded_template: EmailTemplate
) -> None:
    response = client.get("/api/v1/email-templates")
    assert response.status_code == 200
    templates = response.json()
    assert len(templates) == 1
    template = templates[0]
    assert template["key"] == "submission_follow_up"
    assert set(template["placeholders"]) == {"contact", "candidate"}


def test_patch_email_template_updates_name_subject_body(
    client: TestClient, seeded_template: EmailTemplate
) -> None:
    response = client.patch(
        "/api/v1/email-templates/submission_follow_up",
        json={
            "name": "Neuer Name",
            "subject": "Neuer Betreff für {role}",
            "body": "Neuer Text mit {role} und {candidate}.",
        },
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["key"] == "submission_follow_up"
    assert updated["name"] == "Neuer Name"
    assert updated["subject"] == "Neuer Betreff für {role}"
    assert updated["body"] == "Neuer Text mit {role} und {candidate}."
    # Platzhalter spiegeln sofort den neuen Text wider, nicht den alten.
    assert set(updated["placeholders"]) == {"role", "candidate"}

    # Auch ueber die Liste sichtbar (keine gecachte alte Version).
    listed = client.get("/api/v1/email-templates").json()[0]
    assert listed["name"] == "Neuer Name"


def test_patch_email_template_ignores_key_field(
    client: TestClient, seeded_template: EmailTemplate
) -> None:
    """`EmailTemplateUpdate` hat bewusst kein `key`-Feld (siehe schemas/
    operational.py) - ein im Payload mitgeschicktes "key" wird von Pydantic
    stillschweigend ignoriert (extra="ignore" ist der Default), der
    ursprüngliche Key bleibt bestehen."""
    response = client.patch(
        "/api/v1/email-templates/submission_follow_up",
        json={"key": "renamed_key", "name": "Trotzdem gleicher Key"},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["key"] == "submission_follow_up"
    assert updated["name"] == "Trotzdem gleicher Key"

    # Der alte Key ist weiterhin die gueltige Referenz, kein neuer Key wurde
    # angelegt.
    renamed_response = client.patch("/api/v1/email-templates/renamed_key", json={"name": "x"})
    assert renamed_response.status_code == 404


def test_patch_unknown_template_key_returns_404(client: TestClient) -> None:
    response = client.patch("/api/v1/email-templates/does_not_exist", json={"name": "Egal"})
    assert response.status_code == 404


def test_patch_partial_update_leaves_other_fields_unchanged(
    client: TestClient, seeded_template: EmailTemplate
) -> None:
    response = client.patch(
        "/api/v1/email-templates/submission_follow_up", json={"name": "Nur Name geändert"}
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Nur Name geändert"
    assert updated["subject"] == "Feedback zu {candidate}"
    assert "Feedback zu {candidate}?" in updated["body"]
