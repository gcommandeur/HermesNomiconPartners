# DSGVO-Inventur: Personenbezug eines Kandidaten und die Anonymisierung

Stand 2026-10-04 (Review-Nachbesserung Punkt 9). **Reine Bestandsaufnahme, nichts implementiert,
keine Rechtsberatung** - der Nutzer entscheidet danach, ob und wie. Grundlage: die SQLAlchemy-Modelle
(51 Tabellen, per Skript ausgelesen), der Code von `CandidateService.anonymize`
(`backend/src/cc_crm/services/candidates.py`) und die Job-Warteschlange. Nicht gegen
Produktionsdaten geprueft (kein Zugriff): "kann enthalten" heisst, dass das Feld seiner Art nach
Personenbezug haben kann, nicht, dass es ihn in der Praxis hat.

## 1. Was `anonymize` heute tut

Admin-Aktion, der Kandidatendatensatz bleibt (Prozesse, Placements, Statistik). Behandelt wird:

- **Dokumente:** alle Dokumente mit `owner_type="candidate"` (CV, anonymes Profil "Nr. XXXX.docx")
  werden aus dem Speicher geloescht und die Zeilen entfernt.
- **Kandidatenfelder:** `first_name`, `last_name` -> "Anonymisiert"; `anrede`, `consent_received`,
  `cv_available`, `no_gos`, `custom_fields` geleert; auf `NULL` gesetzt: `email`, `phone`,
  `linkedin_url`, `referred_by`, `summary`, `short_profile`, `freitext_notizen`, `wechselgrund`,
  `next_step`.
- **Audit-Log:** `old_values`/`new_values` der Eintraege mit `entity_type="candidate"` werden durch
  "[entfernt]" ersetzt (Trigger-Umgehung nur per transaktionsgebundenem Flag); ein neuer Eintrag
  `anonymized` ohne Personenwerte.

Alles andere in diesem Dokument wird **nicht** angefasst.

## 2. Tabelle `candidates` - Spalte fuer Spalte

| Spalte | Personenbezug | Von `anonymize` behandelt? | Anmerkung |
|---|---|---|---|
| `first_name`, `last_name` | direkt | **ja** ("Anonymisiert") | |
| `anrede` | direkt (Geschlecht) | **ja** | |
| `email`, `phone`, `linkedin_url` | direkt (Kontakt) | **ja** | |
| `referred_by` | Dritte (Empfehler) | **ja** | |
| `summary`, `short_profile`, `freitext_notizen`, `wechselgrund`, `next_step` | Freitext, kann alles enthalten | **ja** | `short_profile` = anonymisierter Profiltext, nicht auf Anonymitaet geprueft |
| `custom_fields` | Freitext/Zusatzfelder | **ja** | |
| `no_gos` | Praeferenzen | **ja** | |
| `consent_received`, `cv_available` | Einwilligung/Status | **ja** (auf false) | der Einwilligungsnachweis geht damit verloren |
| **`cv_extraction_raw`** | **komplettes KI-Rohergebnis aus dem CV** (Name, Arbeitgeber, Stationen, Ausbildung ...) | **NEIN** | **groesste Luecke**: wird beim CV-Auslesen gespeichert und bleibt nach der Anonymisierung vollstaendig stehen |
| `berufliche_stationen` (JSON) | Arbeitgeber, Zeitraeume, Taetigkeiten | **nein** | stark identifizierend |
| `current_employer_internal` | aktueller Arbeitgeber | **nein** | identifizierend |
| `examensnoten`, `ausbildung_titel`, `abschluesse`, `rechtsgebiete` | Qualifikation | **nein** | in Kombination identifizierend |
| `salary_expectation`, `notice_period` | Gehalt, Kuendigungsfrist | **nein** | |
| `aktuelles_umfeld_kanzleityp`, `aktuelles_umfeld_kanzleigroesse`, `passender_kanzleityp`, `remote_teilzeit_wuensche` | Praeferenzen/Umfeld | **nein** | geringer bis mittlerer Bezug |
| `city`, `postal_code` | Wohnort | **nein** | Quasi-Identifikator (bewusst fuer Statistik/Umkreissuche behalten) |
| `job_title`, `qualification`, `fachliche_schwerpunkte`, `edv_kenntnisse`, `rollen`, `rollen_unbestaetigt` | Beruf/Kenntnisse | **nein** | strukturiert, fuer Statistik behalten |
| `available_from`, `last_contact_at`, `cv_in_recorded_at`, `status` | Verlauf | **nein** | |
| `candidate_number` | Pseudonym ("Nr. XXXX") | **nein** | bleibt als Schluessel; verknuepft mit alten, bereits versendeten anonymen Profilen |
| `owner_user_id` | internes Personal | nicht relevant | Mitarbeiter, kein Kandidatenbezug |

## 3. Andere Tabellen mit Bezug zum Kandidaten

| Tabelle (Spalten mit Personenbezug) | Bezug | Behandelt? | Anmerkung |
|---|---|---|---|
| `documents` (Dateien im Speicher) | `owner_type="candidate"` | **ja** | Dateien und Zeilen geloescht |
| `audit_logs` (`old_values`, `new_values`) | `entity_type="candidate"` | **teilweise** | nur Eintraege mit Typ `candidate` geschwaerzt; Eintraege anderer Typen (z. B. `candidate_submission` mit alten/neuen Werten von `summary`, `next_step`, `feedback_summary`) bleiben |
| `notes` (`body`) | `candidate_id`, `candidate_submission_id` | **nein** | Notizen/Kommentare, Autor als FK/Text |
| `activities` (`subject`, `details`) | `candidate_id`, `candidate_submission_id` | **nein** | Verlauf (Anrufe, Mails) |
| `tasks` (`title`, `description`) | `candidate_id`, `candidate_submission_id` | **nein** | |
| `mail_messages` (`from_name`, `from_address`, `subject`, `body_text`) | `matched_candidate_id` | **nein** | eingelesene und gesendete Mails mit voller Textbasis |
| `email_draft_logs` (`recipient`, `subject`, `body`) | `candidate_id` | **nein** | gespeicherte Mail-Entwuerfe |
| `calendar_events` (`attendee_email`, `attendee_name`, `invite_message`, `notes`, `title`, `location`) | `candidate_id` | **nein** | Interview-Einladungen: Kontaktdaten des Kandidaten; zusaetzlich liegt der Termin im Outlook des Nutzers (`external_graph_event_id`) |
| `candidate_pitch_logs` (`notes_text`, `next_step`) | `candidate_id` | **nein** | |
| `candidate_submissions` (`summary`, `sent_profile_text`, `feedback_summary`, `next_step`) | `candidate_id` | **nein** | `sent_profile_text` = der an die Kanzlei gesendete Profiltext |
| `submission_feedback` (`feedback_text`, `next_step`, `created_by`) | ueber Prozess | **nein** | Kanzlei-Rueckmeldungen ueber die Person |
| `interviews` (`participants` JSON, `notes`, `location_or_link`) | ueber Prozess | **nein** | Teilnehmernamen |
| `offers` (`notes`), `placements`, `fees` | ueber Prozess | **nein** | `placements`/`fees` sind geschaeftliche Daten (Aufbewahrung, siehe Abschnitt 5) |
| `sourcing_leads` (`source_url`, `current_employer`, `raw_data`, `notes_text`) | `created_candidate_id`, `duplicate_of_candidate_id` | **nein** | eingesammelte Rohdaten ueber die Person |
| `sequence_enrollments` (`stopped_reason`) | `candidate_id` | **nein** | nur ID-Bezug, wenig Text |
| `ai_proposals` (`payload` JSON: Notiz-/Mail-Entwurfstext, Empfaenger) | `target_type="candidate"` | **nein** | Claude-Vorschlaege inkl. Entwurfstexte und Entscheidungsnotiz |
| `mailing_groups` (`recipients` JSON) | enthaelt gespeicherte Empfaengerlisten | **nein** | kann Name/E-Mail des Kandidaten enthalten; kein Fremdschluessel, nicht auffindbar ueber `candidate_id` |
| `cv_extraction_jobs` (`result` JSON) | nur `owner_user_id` | **nein** | KI-Ergebnis eines CV-Scans (Name, Stationen ...), **ohne Kandidatenbezug** - nicht gezielt loeschbar; Aufbewahrungsdauer unklar |
| `background_jobs` (`payload`, **`payload_blob`**) | `cv.scan`-Jobs | **nein** | `payload_blob` = die CV-Datei; wird nur bei **erfolgreichem** Abschluss geleert - bei einem endgueltig **fehlgeschlagenen** Job bleibt der Lebenslauf dauerhaft in der Tabelle; `payload.filename` kann den Namen enthalten |
| `deletion_requests` (`requested_via`) | `candidate_id` | nicht relevant | der Loeschantrag selbst, als Nachweis sinnvoll zu behalten |
| `webhook_deliveries` (`payload`), `event_outbox` | nur IDs | **unkritisch** | Nutzlast enthaelt bewusst nur `entity_type`, `entity_id`, `audit_log_id` (Entscheidung E4) |

## 4. Ausserhalb der Datenbank

- **Dokumentenspeicher:** CV und anonymes Profil werden beim Anonymisieren geloescht (siehe oben); sonstige Kopien (z. B. an Kanzleien gesendete Mail-Anhaenge) liegen in fremden Postfaechern.
- **Datenbank-Sicherungen** (`backend/scripts/backup_to_s3.py` bzw. Provider-Backups) enthalten den Stand vor der Anonymisierung bis zum Ablauf der Aufbewahrungsfrist der Sicherung.
- **Outlook/Teams:** Termine und gesendete Mails liegen in den Konten der Mitarbeiter (Graph-Kalender, Gesendet-Ordner); Hermes kann sie nicht zurueckholen.
- **Claude/MCP:** nur lesend und nur bei eingeschalteter Schnittstelle; was Claude abgerufen hat, liegt im Gespraech des Nutzers bei Anthropic (Auftragsverarbeitung, siehe `PROJEKT_STAND.md`).
- **Protokolle/Sentry:** Anfrage-Logs enthalten Pfade und Nutzer-ID, keine Request-Bodys.

## 5. Zusammenfassung und offene Entscheidungen

**Behandelt:** Identitaets- und Kontaktfelder, Freitexte der Kandidatentabelle, Zusatzfelder, Dokumente
im Speicher, Audit-Werte des Kandidaten.

**Nicht behandelt, nach Gewicht (Vorschlag der Reihenfolge, wenn der Nutzer umsetzen will):**
1. `cv_extraction_raw` (komplettes CV-Ergebnis) und das **liegen gebliebene `payload_blob`** fehlgeschlagener Scan-Jobs.
2. `berufliche_stationen`, `current_employer_internal`, `examensnoten`, `salary_expectation`, `notice_period` (strukturierte, stark identifizierende Felder).
3. Texte an Prozessen und Verlauf: `notes`, `activities`, `tasks`, `submission_feedback`, `interviews`, `candidate_submissions` (Texte), `candidate_pitch_logs`, `ai_proposals`.
4. Kommunikation: `mail_messages`, `email_draft_logs`, `calendar_events` (Teilnehmer), `mailing_groups`.
5. Audit-Eintraege anderer Objekttypen mit alten/neuen Textwerten; `sourcing_leads`; `cv_extraction_jobs`.

**Fragen, die der Nutzer klaeren muss (rechtlich/fachlich, nicht technisch):**
- Loeschen oder schwaerzen? Was bleibt fuer Statistik (Ort, Beruf, Status) erlaubt, ohne dass die Person bestimmbar bleibt?
- Aufbewahrungspflichten fuer Honorar/Rechnung (`placements`, `fees`) und den Einwilligungsnachweis (`consent_received` wird derzeit mit geloescht).
- Umgang mit Sicherungen und mit Kopien in Outlook/Fremdpostfaechern.
- `candidate_number` als Pseudonym behalten (verbindet mit bereits versendeten anonymen Profilen) oder nicht.

## 6. Nicht verifiziert

- Inhalt echter Daten (kein Produktionszugriff): was in `short_profile`, `notes`, `activities`, `cv_extraction_raw` tatsaechlich steht.
- Ob der Speicher (Bucket) weitere abgeleitete Dateien (Vorschaubilder o. ae.) ablegt - im Code wurde keine gefunden.
- Ob die Tabellen `mailing_groups.recipients` und `cv_extraction_jobs.result` in der Praxis Personenbezug enthalten; sie haben keinen Kandidatenbezug und lassen sich nur durch Durchsuchen des Inhalts finden.
