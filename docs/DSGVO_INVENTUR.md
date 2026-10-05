# DSGVO-Inventur: Personenbezug eines Kandidaten und die Anonymisierung

Stand 2026-10-05. Der Abschnitt 1 beschreibt `anonymize` nach der Erweiterung vom 2026-10-05 (zweite
Stufe, Einwilligungsnachweis); Abschnitt 7 ist eine **reine Bestandsaufnahme mit Vorschlaegen, nichts
implementiert, keine Rechtsberatung** - der Nutzer entscheidet danach, ob und wie. Grundlage: die SQLAlchemy-Modelle
(51 Tabellen, per Skript ausgelesen), der Code von `CandidateService.anonymize`
(`backend/src/cc_crm/services/candidates.py`) und die Job-Warteschlange. Nicht gegen
Produktionsdaten geprueft (kein Zugriff): "kann enthalten" heisst, dass das Feld seiner Art nach
Personenbezug haben kann, nicht, dass es ihn in der Praxis hat.

## 1. Was `anonymize` heute tut

Admin-Aktion, der Kandidatendatensatz bleibt (Prozesse, Placements, Statistik). Behandelt wird:

- **Dokumente:** alle Dokumente mit `owner_type="candidate"` (CV, anonymes Profil "Nr. XXXX.docx")
  werden aus dem Speicher geloescht und die Zeilen entfernt.
- **Zweite Stufe (seit 2026-10-05):** zusaetzlich geleert werden `cv_extraction_raw` (NULL),
  `berufliche_stationen` (leere Liste), `current_employer_internal`, `examensnoten`,
  `salary_expectation`, `notice_period` (NULL).
- **Einwilligungsnachweis (seit 2026-10-05):** `consent_received` faellt auf `false` (an einen
  anonymisierten Datensatz darf nichts mehr gehen), der NACHWEIS bleibt ohne Personenbezug:
  `consent_recorded_at` (wann das Flag in Hermes auf `true` ging, einmal gestempelt),
  `consent_source` (derzeit `hermes_manuell`), `anonymized_at`, die pseudonyme Kennung
  `candidate_number`, und der Audit-Eintrag `anonymized` traegt `consent_was_given`,
  `consent_recorded_at`, `consent_source`. **Altbestand:** wo das Flag ohne Datum gesetzt war, bleibt
  das Datum NULL (nicht geraten). Offen/zu klaeren: ob "Datum + Quelle" als Nachweis reicht oder der
  Umfang der Einwilligung (z. B. Weitergabe an Kanzleien) zusaetzlich erfasst werden soll - dafuer gibt
  es heute kein Feld.
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
| **`cv_extraction_raw`** | **komplettes KI-Rohergebnis aus dem CV** (Name, Arbeitgeber, Stationen, Ausbildung ...) | **ja (seit 2026-10-05)** | war die groesste Luecke |
| `berufliche_stationen` (JSON) | Arbeitgeber, Zeitraeume, Taetigkeiten | **ja (seit 2026-10-05)** | leere Liste |
| `current_employer_internal` | aktueller Arbeitgeber | **ja (seit 2026-10-05)** | |
| `examensnoten` | Qualifikation | **ja (seit 2026-10-05)** | |
| `ausbildung_titel`, `abschluesse`, `rechtsgebiete` | Qualifikation | **nein** | strukturiert, fuer Statistik behalten; in Kombination identifizierend |
| `salary_expectation`, `notice_period` | Gehalt, Kuendigungsfrist | **ja (seit 2026-10-05)** | |
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
| `background_jobs` (`payload`, **`payload_blob`**) | `cv.scan`-Jobs | **ja (seit 2026-10-05)** | Bytes und `payload.filename` werden beim endgueltigen Fehlschlag und beim Worker-Absturz im letzten Versuch geloescht; `scripts/purge_job_blobs.py` (Probelauf als Standard) raeumt Altbestand und verwaiste Jobs nach 3 Tagen auf - **noch nicht gegen Produktion ausgefuehrt** |
| `deletion_requests` (`requested_via`) | `candidate_id` | nicht relevant | der Loeschantrag selbst, als Nachweis sinnvoll zu behalten |
| `webhook_deliveries` (`payload`), `event_outbox` | nur IDs | **unkritisch** | Nutzlast enthaelt bewusst nur `entity_type`, `entity_id`, `audit_log_id` (Entscheidung E4) |

### 3a. Neue Datenkategorie: Vorstellungs-Archiv (seit 2026-10-05)

Tabelle `presentation_records` (+ `presentation_removal_requests`) und Dateien unter dem Speicher-
Praefix `presentation-archive/`. **Zweck:** Nachweis im Honorar-Streitfall, was bei einer Vorstellung an
eine Kanzlei gegangen ist. **Inhalt je Versand:** Empfaenger-Adresse(n), Betreff, Mailtext, Message-ID,
Versender (Mitarbeiter), die exakten versendeten Anhaenge mit SHA-256, der Profiltext zum Versandzeitpunkt,
die Kandidatennummer (Pseudonym), Name der Kanzlei, optional Prozess-ID. **Rechtsgrundlage (Vorschlag):**
berechtigtes Interesse (Art. 6 Abs. 1 lit. f DSGVO) am Nachweis des Honoraranspruchs; Interessenabwaegung
und Aufnahme ins Verarbeitungsverzeichnis sind Sache des Nutzers - keine Rechtsberatung.

- **Zugriff:** ausschliesslich Admins; fuer alle anderen antworten die Routen mit 404. Nicht in
  Dokumentenlisten, Suche, Exporten, Webhooks oder der MCP-Ausgabe.
- **Bewusst NICHT von der Anonymisierung oder einer Teil-Loeschung beruehrt:** der Nachweis soll genau dann
  noch da sein, wenn der Kandidat nicht mehr identifizierbar im System steht. Er enthaelt aber weiterhin
  den versendeten Text und die Dateien (anonymes Profil, ggf. mit Hinweisen auf die Person). Das ist eine
  bewusste Ausnahme von Abschnitt 1 und muss in der Datenschutzinformation und beim Loeschkonzept
  beruecksichtigt werden.
- **Keine Fremdschluessel:** ueberlebt auch das endgueltige Loeschen von Kandidat, Kanzlei oder Prozess.
- **Unveraenderlich** (Postgres-Trigger) bis auf die Aufbewahrungsfrist `retention_until`.
- **Aufbewahrung offen:** `retention_until` setzt der Admin je Eintrag; es gibt keine Standardfrist und
  keine automatische Loeschung. Entfernen nur nach Ablauf der Frist, mit Begruendung und Freigabe durch einen
  zweiten Admin (Audit-Eintrag ohne Personendaten). **Zu klaeren (Nutzer):** welche Frist (z. B.
  Verjaehrung der Honoraranspruchs plus Puffer) und ob sie beim Versand automatisch vorbelegt werden soll.
- **Sicherungen/Betrieb:** der Trigger schuetzt gegen die laufende Software, nicht gegen Eigentuemer-
  Zugang zur Datenbank; Datenbank-Sicherungen und der Objektspeicher (`presentation-archive/`) fallen unter
  dieselben Aufbewahrungsfristen wie die Eintraege.
- **Kein Backfill:** fuer Vorstellungen vor dem 2026-10-05 existiert kein Beleg. Die Zaehlung
  `GET /admin/presentation-archive/count-without-record` nennt, wie viele Prozesse ab `cv_out` ohne
  Eintrag dastehen.

## 4. Ausserhalb der Datenbank

- **Dokumentenspeicher:** CV und anonymes Profil werden beim Anonymisieren geloescht (siehe oben); sonstige Kopien (z. B. an Kanzleien gesendete Mail-Anhaenge) liegen in fremden Postfaechern.
- **Datenbank-Sicherungen** (`backend/scripts/backup_to_s3.py` bzw. Provider-Backups) enthalten den Stand vor der Anonymisierung bis zum Ablauf der Aufbewahrungsfrist der Sicherung.
- **Outlook/Teams:** Termine und gesendete Mails liegen in den Konten der Mitarbeiter (Graph-Kalender, Gesendet-Ordner); Hermes kann sie nicht zurueckholen.
- **Claude/MCP:** nur lesend und nur bei eingeschalteter Schnittstelle; was Claude abgerufen hat, liegt im Gespraech des Nutzers bei Anthropic (Auftragsverarbeitung, siehe `PROJEKT_STAND.md`).
- **Protokolle/Sentry:** Anfrage-Logs enthalten Pfade und Nutzer-ID, keine Request-Bodys.

## 5. Zusammenfassung und offene Entscheidungen

**Behandelt:** Identitaets- und Kontaktfelder, Freitexte der Kandidatentabelle, Zusatzfelder, Dokumente
im Speicher, Audit-Werte des Kandidaten, seit 2026-10-05 auch `cv_extraction_raw`, Stationen,
aktueller Arbeitgeber, Examensnoten, Gehalt/Kuendigungsfrist und die Bytes fehlgeschlagener Scan-Jobs.

**Nicht behandelt, nach Gewicht (Vorschlag der Reihenfolge, wenn der Nutzer umsetzen will):**
1. ~~`cv_extraction_raw` und `payload_blob`~~ - erledigt 2026-10-05.
2. ~~`berufliche_stationen`, `current_employer_internal`, `examensnoten`, `salary_expectation`, `notice_period`~~ - erledigt 2026-10-05.
3. Texte an Prozessen und Verlauf: `notes`, `activities`, `tasks`, `submission_feedback`, `interviews`, `candidate_submissions` (Texte), `candidate_pitch_logs`, `ai_proposals`.
4. Kommunikation: `mail_messages`, `email_draft_logs`, `calendar_events` (Teilnehmer), `mailing_groups`.
5. Audit-Eintraege anderer Objekttypen mit alten/neuen Textwerten; `sourcing_leads`; `cv_extraction_jobs`.

**Fragen, die der Nutzer klaeren muss (rechtlich/fachlich, nicht technisch):**
- Loeschen oder schwaerzen? Was bleibt fuer Statistik (Ort, Beruf, Status) erlaubt, ohne dass die Person bestimmbar bleibt?
- Aufbewahrungspflichten fuer Honorar/Rechnung (`placements`, `fees`). Der Einwilligungsnachweis bleibt seit 2026-10-05 als Datum + Quelle + Pseudonym stehen (Abschnitt 1); ob das rechtlich reicht, ist zu klaeren.
- Umgang mit Sicherungen und mit Kopien in Outlook/Fremdpostfaechern.
- `candidate_number` als Pseudonym behalten (verbindet mit bereits versendeten anonymen Profilen) oder nicht.

## 6. Nicht verifiziert

- Inhalt echter Daten (kein Produktionszugriff): was in `short_profile`, `notes`, `activities`, `cv_extraction_raw` tatsaechlich steht.
- Ob der Speicher (Bucket) weitere abgeleitete Dateien (Vorschaubilder o. ae.) ablegt - im Code wurde keine gefunden.
- Ob die Tabellen `mailing_groups.recipients` und `cv_extraction_jobs.result` in der Praxis Personenbezug enthalten; sie haben keinen Kandidatenbezug und lassen sich nur durch Durchsuchen des Inhalts finden.

## 7. Freitext zu Kandidaten in Verlauf und Kommunikation (Vorschlaege, noch NICHTS geaendert)

Auftrag vom 2026-10-05: fuer jede Tabelle mit Kandidatenbezug die Textfelder auflisten, die bei der
Anonymisierung heute **stehen bleiben**, mit Risiko und Vorschlag. **Die Entscheidung trifft der Nutzer;
hier ist nichts geloescht oder veraendert.** Grundlage: die Modelle (Spalten per Skript ausgelesen), nicht
gegen Produktionsdaten geprueft - "Risiko" beschreibt, was in dem Feld stehen *kann*.

Bedeutung der Vorschlaege: **loeschen** = Feld/Zeile entfernen (Text weg, Zeile bleibt fuer Zaehlungen
oder faellt ganz weg); **schwaerzen** = Text durch "[entfernt]" ersetzen, Zeile und strukturierte Daten
bleiben; **behalten** = bleibt, mit Begruendung. Ein Teil der Daten ist zugleich Geschaeftsdaten der
Kanzlei-Beziehung (Rueckmeldung einer Kanzlei ueber einen Prozess); dort ist die Abwaegung
Betroffenenrecht gegen berechtigtes Interesse eine rechtliche Frage.

| Tabelle | Feld | Risiko | Vorschlag |
|---|---|---|---|
| `notes` | `body` | **hoch**: freie Notizen/Kommentare zur Person (Gespraechsinhalte, Gruende, Familiaeres); fuer alle sichtbar | **loeschen** (Zeilen mit `candidate_id`); Notizen, die nur ueber `candidate_submission_id` haengen, mitnehmen |
| `activities` | `subject`, `details` | **hoch**: Anruf-/Mail-Verlauf, oft mit Namen und Inhalten | **schwaerzen** (`subject`, `details`); `activity_type` und Zeitpunkt behalten (Aktivitaetsstatistik, Cockpit) |
| `activities` | `activity_type` | niedrig (Enum-artig: call, mail ...) | **behalten** (Statistik) |
| `tasks` | `title`, `description` | **mittel**: oft "Erika anrufen", Rueckrufgrund | **schwaerzen**; `status`, `priority`, Faelligkeit behalten (Auswertung) |
| `tasks` | `resolution_outcome` | niedrig bis mittel (kurzer Freitext) | **schwaerzen** |
| `submission_feedback` | `feedback_text`, `next_step`, `created_by` | **hoch**: Bewertung der Person durch die Kanzlei im Wortlaut; zugleich Geschaeftsvorgang mit Kanzlei | **schwaerzen** `feedback_text`/`next_step`; `feedback_type`, `stage` und Zeit behalten (Prozess-Statistik). `created_by` ist ein Mitarbeiter, kein Kandidatenbezug: **behalten** |
| `interviews` | `participants` (JSON) | **hoch**: Teilnehmernamen (auch der Kandidat) | **schwaerzen** (Liste leeren oder Namen ersetzen) |
| `interviews` | `notes`, `location_or_link` | **mittel bis hoch**: Gespraechsnotizen; Link/Ort kann Namen oder Raumbezug enthalten | `notes`: **schwaerzen**; `location_or_link`: **schwaerzen**; `interview_type`, `status`, Termin **behalten** |
| `candidate_submissions` | `summary`, `feedback_summary`, `next_step` | **hoch**: Zusammenfassung/Stand zur Person im Prozess | **schwaerzen** |
| `candidate_submissions` | `sent_profile_text` | **hoch**: der an die Kanzlei gesendete (anonymisierte) Profiltext, nicht auf Anonymitaet geprueft; entspricht inhaltlich `short_profile`, das schon geleert wird | **schwaerzen** (gleiche Behandlung wie `short_profile`) |
| `candidate_submissions` | `salary_at_submission`, `refund_terms` | **mittel**: Gehalt der Person bzw. vertragliche Rueckerstattungsbedingungen | `salary_at_submission`: **schwaerzen** (wie `salary_expectation`); `refund_terms`: **behalten** (Vertragsbedingung der Kanzlei, kein Personenbezug, Honorar-Aufbewahrung) |
| `candidate_submissions` | `owner` (String), `status`, `cancellation_reason`, `closing_status` | niedrig (Mitarbeiter bzw. Enum-Werte) | **behalten** (Statistik, Abrechnung) |
| `ai_proposals` | `payload` (JSON) | **hoch**: Entwurfstext einer Notiz/Mail, Empfaenger | **loeschen** der `payload`-Inhalte fuer `target_type="candidate"` (Zeile mit Status/Zeit darf bleiben) |
| `ai_proposals` | `decision_note` | **niedrig bis mittel** (Freitext des Entscheiders) | **schwaerzen** |
| `mail_messages` | `from_name`, `from_address` | **hoch**: Name und E-Mail der Person (bei eingehenden Mails); bei ausgehenden der Mitarbeiter | **schwaerzen** fuer `matched_candidate_id`-Zeilen; ausgehende Mails: Empfaenger steht im Text, siehe `body_text` |
| `mail_messages` | `subject`, `body_text`, `parse_error` | **hoch**: voller Mailtext inkl. Signatur mit Telefon/Adresse; `parse_error` kann Auszuege des Rohtexts enthalten | **loeschen** (Zeilen mit `matched_candidate_id`); Mails sind zusaetzlich im IMAP-Postfach/Outlook des Mitarbeiters, nicht in Hermes loeschbar |
| `mail_messages` | `message_id`, `imap_uid`, `is_linkedin`, `match_status`, `direction` | niedrig (technische Kennungen) | **behalten** oder mit der Zeile loeschen |
| `email_draft_logs` | `recipient`, `subject`, `body` | **hoch**: Empfaenger-Adresse und Text eines gesendeten/gespeicherten Entwurfs | **loeschen** (Zeilen mit `candidate_id`); `template_key`, `provider` unkritisch |
| `calendar_events` | `attendee_email`, `attendee_name` | **hoch**: Kontaktdaten der Person | **loeschen** (auf NULL) |
| `calendar_events` | `invite_message`, `notes`, `title`, `location`, `online_meeting_url` | **mittel bis hoch**: Einladungstext, Notizen, Titel mit Namen ("Interview Erika M."), Meeting-Link | **schwaerzen**; Beginn/Ende/`event_type` **behalten** (Kapazitaet, Statistik). Der Termin liegt zusaetzlich im Outlook des Mitarbeiters (`external_graph_event_id`) - dort nicht von Hermes loeschbar |

**Wie die Zeilen gefunden werden:** `notes`, `activities`, `tasks`, `email_draft_logs`, `calendar_events` ueber
`candidate_id` (und ueber `candidate_submission_id` der Prozesse des Kandidaten); `submission_feedback` und
`interviews` NUR ueber `submission_id` -> `candidate_submissions.candidate_id`; `mail_messages` ueber
`matched_candidate_id` (nicht zugeordnete Mails ohne Kandidatenbezug sind per Schluessel nicht auffindbar);
`ai_proposals` ueber `target_type="candidate"` und die Ziel-ID im `payload`.

**Zu entscheiden (Nutzer):**
1. Pauschal *schwaerzen statt loeschen* fuer alles mit Prozessbezug (erhaelt Zaehlungen, Cockpit, Honorar-
   Nachweise), *loeschen* fuer reine Kommunikation (`mail_messages`, `email_draft_logs`, Notizen,
   `ai_proposals`)? Das ist der Standardvorschlag.
2. Soll die Rueckmeldung einer Kanzlei (`submission_feedback`) wegen deren berechtigtem Interesse bleiben?
3. Sollen Mails ohne Zuordnung (kein `matched_candidate_id`), die den Namen im Text tragen, per Volltext
   gesucht werden? (Aufwand und Fehlerquote hoch; Vorschlag: nein, sondern Aufbewahrungsfrist fuer das
   Postfach.)
4. Reicht "Datum + Quelle + Pseudonym" als Einwilligungsnachweis, oder soll der Umfang erfasst werden?
5. Reihenfolge/Umfang einer Umsetzung (eigener Auftrag; die Anonymisierung ist eine Admin-Aktion und nicht
   rueckgaengig zu machen - vor einer Erweiterung auf einer Kopie der Produktionsdaten im Probelauf pruefen).
