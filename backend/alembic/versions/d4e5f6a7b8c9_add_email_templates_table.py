"""add email_templates table, seed 13 existing + 12 new mail templates

Revision ID: d4e5f6a7b8c9
Revises: b3f8c1d2e4a5
Create Date: 2026-09-16

Verlagert die bisher hartcodierte EmailWorkflowService.TEMPLATES-Liste
(backend/src/cc_crm/services/operational.py) in die DB, damit Name/Betreff/
Text im CRM editierbar sind (Auftrag "Mailvorlagen editierbar machen").

Seed enthaelt:
- Die 13 bestehenden Vorlagen UNVERAENDERT (gleicher key/name/subject/body
  wie vorher im Code) - MailingGroup.template_key referenziert diese Keys
  bereits per String (kein FK), keine bestehende Zuordnung bricht.
- 12 neue Vorlagen aus der Mail-Kategorisierung des Lukas-Postfach-Exports
  (siehe Lukas_Mail_Kategorien_Report.md) + einer Datenschutz-Einwilligungs-
  Vorlage, anonymisiert/in Platzhalterform.

Platzhalter-Tokens (z.B. "{candidate}") bleiben literal im Text stehen und
werden NICHT hier gespeichert - sie werden zur Laufzeit per Regex aus
subject+body extrahiert (siehe EmailWorkflowService.extract_placeholders),
damit sie nach einer Bearbeitung im CRM immer den tatsaechlichen
Vorlageninhalt widerspiegeln, nicht eine hier eingefrorene Momentaufnahme.
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "b3f8c1d2e4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_templates")),
    )
    op.create_index(op.f("ix_email_templates_key"), "email_templates", ["key"], unique=True)

    email_templates = sa.table(
        "email_templates",
        sa.column("id", sa.Uuid()),
        sa.column("key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("subject", sa.String()),
        sa.column("body", sa.Text()),
    )
    op.bulk_insert(
        email_templates,
        [
            {
                "id": uuid.UUID("d5de7013-8dbc-4702-973c-82d3ad44e43c"),
                "key": "post_qualification_call",
                "name": "Nach Quali Call",
                "subject": "Vielen Dank für das Gespräch, {candidate}",
                "body": "Guten Tag {candidate},\n\nvielen Dank für das offene und informative Gespräch eben. Ich habe ein gutes Bild von Ihrem Profil und Ihren Vorstellungen gewinnen können.\n\nNächster Schritt: {next_step}\n\nIch melde mich, sobald es Neuigkeiten gibt. Bei Rückfragen erreichen Sie mich jederzeit.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("8f25f6d2-183b-4c00-b3f7-0d7276f25e85"),
                "key": "request_cv",
                "name": "CV nachfordern",
                "subject": "Unterlagen zu Ihrem Profil",
                "body": "Guten Tag {candidate},\n\num Ihr Profil vollständig vorstellen zu können, fehlen mir noch aktuelle Unterlagen (Lebenslauf/Zeugnisse). Könnten Sie mir diese bei Gelegenheit zusenden?\n\nVielen Dank und beste Grüße",
            },
            {
                "id": uuid.UUID("752d3d72-836a-4714-bfed-41ea2761c23c"),
                "key": "profile_approval",
                "name": "Kurzprofil freigeben",
                "subject": "Freigabe Ihres Kurzprofils",
                "body": "Guten Tag {candidate},\n\nanbei finden Sie das anonymisierte Kurzprofil, das ich potenziellen Kanzleien vorstellen möchte:\n\n{short_profile}\n\nBitte prüfen Sie den Text kurz und geben Sie mir Bescheid, ob ich ihn so verwenden darf oder ob noch etwas angepasst werden soll.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("70018aa0-b5fc-47fd-a716-c3d6b44a2227"),
                "key": "candidate_submission",
                "name": "CV-Out Vorstellung",
                "subject": "Profilvorstellung: {candidate} – {role}",
                "body": "Guten Tag {contact},\n\nich möchte Ihnen folgendes Profil für die Position {role} vorstellen:\n\n{short_profile}\n\nGehaltsvorstellung: {salary}\nKündigungsfrist: {notice_period}\n\nDie vollständigen Unterlagen finden Sie im Anhang. Über Ihre Rückmeldung, ob Sie {candidate} kennenlernen möchten, freue ich mich.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("74222689-0ddb-4f46-9ad2-eefc14e1f503"),
                "key": "submission_follow_up",
                "name": "CV-Out nachfassen",
                "subject": "Feedback zu {candidate}",
                "body": "Guten Tag {contact},\n\nich wollte kurz nachfragen, ob Sie das Profil von {candidate} bereits prüfen konnten und ob Interesse an einem Kennenlernen besteht.\n\nÜber eine kurze Rückmeldung würde ich mich freuen.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("0bf5b706-c568-4547-872e-4a61d789320a"),
                "key": "interview_confirmation",
                "name": "Interview bestätigen",
                "subject": "Interviewtermin bei {client}",
                "body": "Guten Tag {contact},\n\nhiermit bestätige ich den vereinbarten Interviewtermin für {candidate} bei {client}.\n\nNächster Schritt: {next_step}\n\nBitte geben Sie mir Bescheid, falls sich am Termin noch etwas ändert.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("7cb80a4d-2a68-4ab8-9d3b-e2e587588b8d"),
                "key": "interview_feedback",
                "name": "Interviewfeedback nachfassen (Kanzlei)",
                "subject": "Kurzes Feedback zum Interview mit {candidate}",
                "body": "Guten Tag {contact},\n\nwie war Ihr Eindruck vom Gespräch mit {candidate}? Über eine kurze Rückmeldung - positiv wie kritisch - würde ich mich freuen, damit wir den Prozess zeitnah fortsetzen können.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("144d3dc1-1e42-4d98-af8a-15eeef24524b"),
                "key": "interview_feedback_candidate",
                "name": "Interviewfeedback nachfassen (Kandidat)",
                "subject": "Rückmeldung zu Ihrem Interview bei {client}",
                "body": "Guten Tag {candidate},\n\nvielen Dank, dass Sie sich Zeit für das Gespräch bei {client} genommen haben. Ich wollte kurz nachfragen, wie Sie das Interview erlebt haben, und Sie über den aktuellen Stand informieren.\n\nNächster Schritt: {next_step}\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("9320d032-de81-4476-bd39-c800b98014b3"),
                "key": "offer_follow_up",
                "name": "Offer nachfassen",
                "subject": "Abstimmung zum Angebot",
                "body": "Guten Tag {contact},\n\nwie ist der aktuelle Stand beim Angebot für {candidate}? Gibt es von Ihrer Seite noch offene Punkte, die wir gemeinsam klären sollten?\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("b694b769-29b9-4224-bddc-1887e2877f3a"),
                "key": "candidate_rejection",
                "name": "Absage Kandidat",
                "subject": "Rückmeldung zum Prozess",
                "body": "Guten Tag {candidate},\n\nleider muss ich Ihnen mitteilen, dass sich {client} für einen anderen Kandidaten entschieden hat. Ich weiß, das ist keine schöne Nachricht.\n\nIch halte weiterhin Ausschau nach passenden Positionen für Sie und melde mich, sobald es Neuigkeiten gibt.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("5412ce8f-8978-4069-9a87-be0f2e6a312f"),
                "key": "client_rejection",
                "name": "Absage Kunde",
                "subject": "Rückmeldung zu {candidate}",
                "body": "Guten Tag {contact},\n\n{candidate} hat sich nach reiflicher Überlegung gegen die Position bei {client} entschieden.\n\nIch halte Sie über weitere passende Profile gerne auf dem Laufenden.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("dd0d913c-2828-42e8-86b6-673ea42c703d"),
                "key": "send_terms",
                "name": "AGB senden",
                "subject": "Zusammenarbeit mit CC",
                "body": "Guten Tag {contact},\n\nvielen Dank für Ihr Interesse an einer Zusammenarbeit. Anbei erhalten Sie unsere Allgemeinen Geschäftsbedingungen zur Prüfung und Unterschrift.\n\nBei Rückfragen stehe ich Ihnen gerne zur Verfügung.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("a734aee6-54fe-48f6-a7dd-786da78c334a"),
                "key": "placement_invoice",
                "name": "Placement / Rechnung",
                "subject": "Erfolgreiche Besetzung",
                "body": "Guten Tag {contact},\n\nvielen Dank für die gute Zusammenarbeit - die Position ist mit {candidate} erfolgreich besetzt. Die Rechnung zur vereinbarten Vermittlungsprovision erhalten Sie anbei.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("94ad83ed-2bc9-4054-bc9b-921a5abb53c7"),
                "key": "cv_blind_submission",
                "name": "CV-Blindversand an Kanzlei",
                "subject": "Kandidat-Nr. {candidate_number} – {role}",
                "body": "Sehr geehrte(r) Herr/Frau {contact},\n\ngerne übersende ich Ihnen das Kurzprofil eines/einer erfahrenen {role} aus dem Raum {location}.\n\n{short_profile}\n\nSollte das Profil für Sie interessant sein, melde ich mich gerne mit weiteren Details bzw. dem vollständigen Lebenslauf.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("cc031698-8cf2-4b16-aa42-faec2c6e6d62"),
                "key": "candidate_availability_note",
                "name": "Kandidaten-Verfügbarkeitsmeldung (ohne Nr.)",
                "subject": "{role} verfügbar",
                "body": "Sehr geehrte(r) Herr/Frau {contact},\n\nich hoffe, es geht Ihnen gut. Wir haben aktuell eine(n) {role}, die/der sich aktuell umorientieren möchte.\n\n{short_profile}\n\nIst das Profil interessant für Sie?\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("f9852c33-67e3-40fd-9e93-52e35d4f9029"),
                "key": "candidate_intro_longform",
                "name": "Kandidatenvorstellung an Kanzlei (Langform)",
                "subject": "Vorstellung erfahrene(r) {role} – {focus_area}",
                "body": "Sehr geehrte Kanzlei {client},\n\ngerne möchten wir Ihnen eine(n) erfahrene(n) {role} ({focus_area}) vorstellen, die/der eine neue berufliche Perspektive im Raum {location} anstrebt.\n\nKandidat-Nr. {candidate_number} – {role} ({focus_area})\n{short_profile}\n\nAnbei senden wir Ihnen unsere AGB. Unsere Konditionen – rein erfolgsorientiert, {commission_percentage}% Provision, keine Mindestfee, ausschließlich Direktvermittlung – lege ich Ihnen zur Prüfung bei.\n\nFür Rückfragen stehe ich jederzeit zur Verfügung.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("323dbc6f-70b6-44de-be70-e06b2d6406ba"),
                "key": "candidate_options_intro",
                "name": "Erstansprache Kandidat: Karriereoptionen",
                "subject": "Optionen in {location}",
                "body": "Sehr geehrte(r) Herr/Frau {candidate},\n\nvielen Dank für das angenehme Gespräch.\n\n{next_step}\n\nIch freue mich auf Ihre Rückmeldung.\n\nViele Grüße",
            },
            {
                "id": uuid.UUID("d7fcb748-010a-4b26-a283-7822680d9800"),
                "key": "call_follow_up",
                "name": "Follow-up nach Telefonat",
                "subject": "Unser Gespräch",
                "body": "Sehr geehrte(r) Herr/Frau {candidate},\n\nvielen Dank für das angenehme Gespräch.\n\nAnbei wie besprochen meine Kontaktdaten.\n\nBei Rückfragen jeglicher Art können Sie sich jederzeit gerne bei mir melden.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("2d823b91-97f2-4bc3-8c4c-c6747f96b6d6"),
                "key": "vacancy_pitch_to_candidate",
                "name": "Vakanz-/Stellenvorstellung an Kandidat",
                "subject": "{role} (m/w/d) bei {client} gesucht",
                "body": "Sehr geehrte(r) Herr/Frau {candidate},\n\neine(n) {role} (m/w/d) bei {client} in {location} sucht aktuell Verstärkung.\n\n{short_profile}\n\nWäre das eine interessante Option für Sie? Ich stehe Ihnen gerne für weitere Details zur Verfügung.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("2cd3e8bf-ad4f-4a83-a3f0-b53db6aca36a"),
                "key": "interview_scheduling_proposal",
                "name": "Terminvereinbarung Interview",
                "subject": "Terminvorschläge {role}",
                "body": "Sehr geehrte(r) Herr/Frau {contact},\n\nfür das Kennenlernen mit {candidate} schlage ich folgende Termine vor:\n\n{appointment_options}\n\nBitte lassen Sie mich wissen, welcher Termin passt, oder nennen Sie mir gerne Alternativen.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("8955b61e-c85c-45c1-996c-a6e02a428802"),
                "key": "client_feedback_request",
                "name": "Feedback-Nachfrage an Kanzlei",
                "subject": "Feedback {candidate}",
                "body": "Sehr geehrte(r) Herr/Frau {contact},\n\nich wollte kurz nachfragen, wie das Gespräch mit {candidate} aus Ihrer Sicht verlaufen ist und ob es bereits eine Rückmeldung zu den nächsten Schritten gibt.\n\nIch freue mich auf Ihre Einschätzung.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("5def9c97-d285-41df-81c6-98c02ab6e835"),
                "key": "contract_dispatch",
                "name": "Versand Vermittlungsvertrag",
                "subject": "Vermittlungsvertrag {client}",
                "body": "Sehr geehrte(r) Herr/Frau {contact},\n\nanbei erhalten Sie den Vermittlungsvertrag für {candidate} / {role} zur Prüfung und Unterschrift.\n\nFür Rückfragen zu den Vertragsdetails stehe ich Ihnen gerne zur Verfügung.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("78703ed2-6b03-47b1-8135-19ad67decde3"),
                "key": "pending_response_reminder",
                "name": "Nachfrage ausstehende Rückmeldung",
                "subject": "Rückmeldung zu {candidate}",
                "body": "Sehr geehrte(r) Herr/Frau {contact},\n\nich wollte kurz nachfragen, ob es bereits eine Rückmeldung zu {candidate} gibt. Sollten noch Unterlagen oder Informationen fehlen, lassen Sie es mich gerne wissen.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("350453b4-0334-451a-96b8-d51f6b64903c"),
                "key": "client_rejection_update_to_candidate",
                "name": "Absage-Mitteilung an Kandidat",
                "subject": "Rückmeldung zu {client}",
                "body": "Sehr geehrte(r) Herr/Frau {candidate},\n\nleider haben wir eine Absage von {client} erhalten.\n\nIch melde mich, sobald ich neue passende Optionen für Sie habe.\n\nBeste Grüße",
            },
            {
                "id": uuid.UUID("940315ad-64ca-4dee-872c-29cce4c3f69f"),
                "key": "gdpr_consent_request",
                "name": "Datenschutz-Einwilligung anfordern",
                "subject": "Kurze Rückfrage zur Zusammenarbeit",
                "body": "Hallo {candidate},\n\ndanke für das angenehme Gespräch – ich freue mich auf die Zusammenarbeit mit Ihnen!\n\nWie besprochen bin ich Ihr Ansprechpartner bei der Commandeur Consulting GmbH und werde nach passenden Vakanzen für Sie suchen. Sobald etwas Passendes dabei ist, melde ich mich oder ein/e Kolleg/in direkt bei Ihnen.\n\nDamit wir offiziell zusammenarbeiten dürfen, brauche ich noch kurz Ihr „Ok“ auf den Datenschutzhinweis per Antwort auf diese E-Mail.\n\nOhne Ihre Einwilligung dürfen wir Ihre Daten nicht verarbeiten oder Ihnen passende Positionen vorstellen.\n\nEin kurzes „Ok“ per Mail als Antwort reicht aus – dann können wir direkt loslegen.\n\nSelbstverständlich können Sie die Zusammenarbeit jederzeit abbrechen – ein kurzer Hinweis genügt, und wir löschen Ihre Daten sofort.\n\nDanke für Ihr Vertrauen – ich freue mich auf den nächsten Schritt mit Ihnen!\n\nViele Grüße\n\n---\n\nDatenschutzhinweis gemäß Art. 13, 14 DSGVO\n\nIm Rahmen unserer Tätigkeit als Personalvermittler verarbeiten wir Ihre personenbezogenen Daten gemäß den geltenden Datenschutzvorschriften, insbesondere gemäß der Datenschutz-Grundverordnung (DSGVO). Verantwortlich für die Verarbeitung ist:\n\nCommandeur Consulting GmbH\n\nZweck der Datenverarbeitung:\nIhre Daten (insbesondere Kontaktdaten, berufliche Qualifikationen, Lebenslauf, Gehaltsvorstellungen, Wechselmotivation etc.) werden ausschließlich zum Zweck der Personalvermittlung und zur Identifikation geeigneter Karriereoptionen verarbeitet. Dies umfasst insbesondere:\n\n- die Kontaktaufnahme per E-Mail, Telefon oder sonstige Kommunikationsmittel\n- die Speicherung Ihrer Daten in unserem internen Bewerbermanagement-System\n- die Vorstellung Ihres Profils bei potenziellen Arbeitgebern – ausschließlich nach vorheriger Rücksprache oder Zustimmung\n- die langfristige Betreuung und Information zu relevanten Stellenangeboten\n\nRechtsgrundlage:\nDie Verarbeitung erfolgt auf Grundlage Ihrer freiwilligen Einwilligung gemäß Art. 6 Abs. 1 lit. a DSGVO. Sie können Ihre Einwilligung jederzeit mit Wirkung für die Zukunft widerrufen.\n\nSpeicherdauer:\nIhre Daten werden über die gesetzlich vorgeschriebene Mindestdauer hinaus gespeichert, um Ihnen auch künftig passende Positionen anbieten zu können. Sollten Sie keine weitere Kontaktaufnahme wünschen, können Sie jederzeit formlos widersprechen – Ihre Daten werden dann unverzüglich gelöscht.\n\nWeitergabe an Dritte:\nEine Weitergabe Ihrer personenbezogenen Daten an Dritte (z. B. potenzielle Arbeitgeber) erfolgt nur nach Ihrer ausdrücklichen Zustimmung. Es findet keine unautorisierte Weitergabe oder Speicherung außerhalb unserer Systeme statt.\n\nIhre Rechte:\nSie haben das Recht auf Auskunft, Berichtigung, Löschung, Einschränkung der Verarbeitung sowie auf Datenübertragbarkeit. Zudem steht Ihnen ein Beschwerderecht bei der zuständigen Aufsichtsbehörde zu.\n\nBei Fragen zum Datenschutz können Sie sich jederzeit an uns wenden.",
            },
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_email_templates_key"), table_name="email_templates")
    op.drop_table("email_templates")
