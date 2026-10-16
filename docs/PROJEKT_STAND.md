# Hermes - Projektstand (Kurzfassung)

Gemeinsame Gedaechtnisstuetze aller Claude-Sitzungen (Laptop und Cloud/Handy). Sitzungen sehen die Gespraeche der jeweils anderen nicht - nur das, was hier und im Repository steht. **Diese Datei ist absichtlich kurz** (jede Sitzung liest sie bei jedem Start).

Weitere Dateien: `PROTOKOLL.md` (jede erledigte Aufgabe, neueste zuerst; nur bei Bedarf, nur die ersten ca. 100 Zeilen lesen), `ENTSCHEIDUNGEN.md` (Entscheidungen ausfuehrlich mit Grund), `ARCHIV_PLAENE.md` (erledigte Plaene, wortgleich archiviert), `DEPLOYMENT.md`, `PLAN_SKALIERUNG.md`.

## Pflicht bei JEDER Aufgabe

1. **Zwei Branches: `entwicklung` (Arbeit) und `main` (Live, deployt nach DigitalOcean).** Keine weiteren anlegen (auch keine `claude/...`). Beide Sitzungen arbeiten und pushen auf `entwicklung`. Direkt auf `main` pusht niemand (in `.claude/settings.json` gesperrt). Nach `main` geht NIE etwas ohne das ausdrueckliche gruene Licht des Nutzers, bei jedem einzelnen Merge.
2. **Vor dem Start:** `git fetch`, auf `entwicklung`, `git pull --rebase origin entwicklung`, dann diese Datei und `CLAUDE.md` lesen.
3. **Am Ende, im selben Commit:** Eintrag OBEN in `docs/PROTOKOLL.md` (Datum, `Laptop`/`Cloud`, was, Commits, was NICHT geprueft wurde, `Gemeldet:` = Kernaussagen an den Nutzer); hier nur Offene Punkte, Entscheidungen (kurz) und Stolperfallen pflegen. Bei Konflikten in den Dateien beide Eintraege behalten.
4. **Sofort pushen** (`git pull --rebase origin entwicklung`, `git push origin entwicklung`), CI abwarten. Eine Aufgabe ist fertig, wenn Tests gruen, **CI gruen** und die Doku stimmt.
5. **Lokaler Branch `main` = `entwicklung`** (Regel des Nutzers, ohne Rueckfrage): nach jeder Aufgabe und dem Push `git branch -f main entwicklung` (ohne auszuchecken). Rein lokal, deployt nichts. **Nicht gedeckt:** `origin/main` (GitHub) - nur mit gruenem Licht.
6. **Nach `main` bringen** (nur auf Freigabe): Pull Request `entwicklung` -> `main`, CI abwarten, **Merge-Commit** (`gh pr merge --merge`, NIE `--rebase`, ohne `--delete-branch`), danach `git merge origin/main` in `entwicklung`. Grund: Rebase schreibt Commits neu, die Kopie `HermesNomiconPartners` bekaeme sie sonst doppelt (Konflikte).
7. Nichts Geheimes eintragen (Passwoerter, Tokens, Verbindungs-Strings, Kunden-/Kandidatendaten). Nie gegen Produktion arbeiten; Produktionsskripte nur der Nutzer, immer erst Dry-Run.

## Wer arbeitet wie

| | Laptop-Sitzung | Cloud-Sitzung (Handy) |
|---|---|---|
| Umgebung | Windows, `backend/.venv`, `corepack pnpm` | Linux, Start-Hook installiert Pakete |
| Git | `entwicklung` | `entwicklung` |
| Nur hier moeglich | Produktions-Skripte, DigitalOcean, lokale Klicktests | - |

Ziel des Nutzers: moeglichst alles vom Handy aus erledigen koennen.

## Uebergabe an die Cloud (2026-10-04, Laptop hoert auf)

Stand: `entwicklung` = Commits `a7907d9` bis `e48bb33` plus Dokumentations-Commit (siehe `PROTOKOLL.md`, 2026-10-05); CI-Stand steht im Protokoll. `origin/main` steht auf `192497c` und ist NICHT nachgezogen - alles seit den Review-Nachbesserungen liegt nur auf `entwicklung`, Merge nach `main` nur mit gruenem Licht. Weiterarbeiten: erst `PROTOKOLL.md` (oberste ca. 15 Eintraege), dann die Liste "Offen (Claude)" unten. Die Kopie `HermesNomiconPartners` liegt nur auf dem Laptop des Nutzers - nicht anfassen. Lehre: Tests, die nur auf Postgres laufen, erst nach gruener CI als fertig melden.

## Offene Punkte

**Wartet auf den Nutzer (nie von Claude):**
- GitHub-Schutzregel fuer `main` (Checks `backend`, `frontend` Pflicht, nur per Pull Request).
- Entra ID: Umleitungs-URI `https://hermescrm-v9sle.ondigitalocean.app/api/v1/auth/microsoft/callback`, delegierte Graph-Berechtigungen, Admin-Zustimmung (`DEPLOYMENT.md` "Outlook & Teams"), danach Login mit echtem Konto testen (Nutzer mit gleicher E-Mail muss existieren).
- DigitalOcean: Pre-Deploy-Job fuer Migrationen + `CC_CRM_MIGRATE_ON_STARTUP=false`; Scheduled Jobs `scripts/send_due_reminders.py` (Cron `0 5 * * *` UTC) und `scripts/run_outreach_sequences.py` (`15 5 * * *`); optional Sentry-DSN.
- Produktions-Skripte in `backend/scripts/` (`cleanup_service_users.py`, `backfill_cv_in_recorded_at.py`, `backfill_cv_available_from_documents.py`, alle Dry-Run) und Zuruecksetzen des `doadmin`-Passworts.
- Auftragsverarbeitung mit Anthropic klaeren, bevor `CC_CRM_AI_ENABLED` eingeschaltet wird (Vorgehen vom Nutzer bestaetigt). `short_profile` geht nur noch mit `CC_CRM_AI_INCLUDE_PROFILE=true` an Claude (Standard aus, entschieden 2026-10-05).
- Produktions-Aufraeumen der Scan-Job-Bytes: `python scripts/purge_job_blobs.py` (Probelauf), danach `--apply` - nur der Nutzer, gegen Produktion nicht von Claude ausgefuehrt.
- Migrationen `f2a4c6e8b0d1` (candidates: Einwilligungsnachweis, `anonymized_at`) und `g3b5d7f9a1c2` (Vorstellungs-Archiv, `mailing_groups.context_candidate_id`, Postgres-Trigger) laufen beim naechsten Deploy mit.
- **Vorstellungs-Archiv:** Aufbewahrungsfrist festlegen (`retention_until` je Eintrag, keine Standardfrist) und klaeren, ob ein einzelner Admin reicht: Entfernen braucht einen ZWEITEN Admin (bei nur einem Admin nicht moeglich). Rechtsgrundlage/Verarbeitungsverzeichnis: `DSGVO_INVENTUR.md` 3a.
- **Nomicon-Modul Überlassung (Details `docs/UEBERLASSUNG.md`):** Scheduled Job `python scripts/run_staffing_deadlines.py` (z. B. `30 5 * * *` UTC) auf DigitalOcean anlegen; AÜG-Erlaubnis unter Überlassung > Compliance eintragen; rechtliche Werte (18/9/3 Monate) und die offenen Fragen mit Fachanwalt klären.
- **Nomicon-Provisionsmodell (`docs/PROVISIONSMODELL.md`, Karriereplan Oktober 2026, seit 2026-10-16 umgesetzt):** offen nur noch der Abgleich mit der Excel (lag nie vor), die Beförderung auf Basis eines Quartals, die Annahme "abgebrochener Einsatz behält den Bonus" und ein Klicktest mit echten Mitarbeiter-/Teamleiter-Logins ("Meine Provision"). Verlängerung = neue Zeile in `staffing_assignment_extensions` (neuer Deal), Bonus und Umsatz immer nach Zahldatum.
- Kopie `HermesNomiconPartners`: lokal ca. 20 Commits vor GitHub, bewusst nicht gepusht; Freigabe zum Pushen offen.

**Offen (Claude):**
1. Offen aus den Review-Nachbesserungen: die echte Microsoft-/Claude-Anbindung live pruefen (haengt an den Punkten des Nutzers oben).
2. Nachmessung bei 200.000 Kandidaten ist erledigt (2026-10-04, Cloud, lokales Postgres): alle sechs Vorgaenge innerhalb der Ziele, Details in `docs/PERFORMANCE.md`. Nicht gemessen: Eigene-Felder-Filter, echte DigitalOcean-Latenz.
3. Start-Hook in einer frischen Cloud-Sitzung gegenpruefen (manuell ok, Start ungetestet).
4. Nicht live im Browser geprueft: Teamleiter-Verwaltung, Freigabe-Inbox, Rechnungen, Sourcing-Umkreis, Kandidaten-Timeline, Prozess-Sperren mit echten Logins, "Geteilt mit" (auch Migration auf Postgres-Kopie).
5. DSGVO: Stufe 2 der Anonymisierung (Kandidatenfelder, Einwilligungsnachweis, Scan-Job-Bytes) ist umgesetzt. Offen, Entscheidung des Nutzers: Verlauf und Kommunikation (`notes`, `activities`, `tasks`, `submission_feedback`, `interviews`, `candidate_submissions`-Texte, `ai_proposals`, `mail_messages`, `email_draft_logs`, `calendar_events`) - Vorschlaege und fuenf Fragen in `docs/DSGVO_INVENTUR.md` Abschnitt 7; noch NICHTS davon geaendert. Ausserdem die uebrigen strukturierten Felder (`ausbildung_titel`, `abschluesse`, `rechtsgebiete`, Umfeld-/Praeferenzfelder) und ob der Einwilligungs-UMFANG erfasst werden soll.
6. Typ-Abweichungen Frontend/Backend: keine mehr (`schema-conformance.ts` ohne Ausnahmeliste); die Demo-Felder sind entfernt.
7. Kopie: `mail_sync.py`/`due_reminders.py` enthalten keinen Firmentext. Konfigurierbar gemacht: Briefkopf-Erkennung (`CC_CRM_AGENCY_LETTERHEAD_MARKER`) und Sourcing-User-Agent (`CC_CRM_COMPANY_NAME`). Offen: Nomicon braucht eine eigene Kandidatenprofil-Vorlage (anonym und offen; `profile_generator.py`-Prompts und `backend/templates/anonymes_profil_master.docx` sind Commandeur-spezifisch) - Muster vom Nutzer noetig, nichts geraten.
9. **Nomicon-Module (2026-10-11, Cloud, Pakete A-I, Details `docs/UEBERLASSUNG.md` und `docs/PROVISIONSMODELL.md`):** Ueberlassung (Modell, Fristen, API, Oberflaeche, Stundenzettel mit Kundenfreigabe per Link, Abrechnung ueber die Freigabe-Inbox, Export, Uebernahme) und Provisionsmodell sind gebaut und per CI/Postgres/Playwright geprueft. Offen: Klicktests mit echten Logins (Mitarbeiter, Teamleiter), Abgleich der Provisionsregeln mit der Excel, rechtliche Pruefung der Fristen, Nomicon-Profilvorlage, DSGVO-Verhalten bei Leiharbeitnehmern.
8. Optional: Browser-Tests (Playwright, Demo-Modus). Kleinigkeiten: Quick-Log auf Kandidat mit offenem Kollegen-Prozess fuehrt dessen Prozess weiter (bewusst); Aktivitaet "Prozess angelegt" hat keinen Autor.

## Zweite Firma: Kopie `HermesNomiconPartners` (Regeln)

- Privates Repo `gcommandeur/HermesNomiconPartners`, mit kompletter Historie. **Seit 2026-10-12 gleichberechtigt und getrennt von Hermes** (kein `upstream`-Merge, eigene Migrationskette, Migrationen duerfen hier entstehen). **Pflicht:** zu Sitzungsbeginn und vor jedem Push `python scripts/vergleich.py --hermes <Klon>` und `docs/VERGLEICH.md` pflegen (Abweichung, Grund, Entscheidung). Bugfixes/Sicherheitsfixes des anderen Repos uebernehmen. Aus Nomicon-Sitzungen wird in Hermes nie geschrieben. Hermes-`CLAUDE.md` sollte dieselbe Regel enthalten (Nutzer traegt ein).
- **Firmenschicht** (gehoert zu Nomicon; `merge=ours` in `.gitattributes` nur noch Altlast): `frontend/src/app/brand-theme.css` (Farbwerte, Seitenhintergrund), `frontend/public/brand/*` (Logos), `backend/templates/*` (Briefkopf). `globals.css` ist Struktur und kommt aus Hermes; neue Design-Variablen in Hermes immer mit Standardwert in `brand-theme.css`.
- **Design-Regel fuer alle Sitzungen:** neue Oberflaeche nur mit den Klassen `brand-*` aus `globals.css` (`bg-brand-panel`, `text-brand-muted`, ...), keine festen Hex-Farben. Firmenname/Logo aus `frontend/src/lib/brand.ts` (`NEXT_PUBLIC_BRAND_*`), Backend `CC_CRM_COMPANY_NAME`, `CC_CRM_PROFILE_TEMPLATE_PATH`. Neue Frontend-Dateien nach dem Rebase einmal `node scripts/brand-colors-codemod.mjs --write` (aus `frontend/`).
- Nomicon-Design (Off-White, Navy-Seitenleiste, Poppins mit `size-adjust 87.5%`) liegt nur lokal in der Kopie. Lokale Vorschau: `starten.local.cmd` / `anmelden.local.cmd` (Git-ausgeschlossen, nur Dummy-Datenbank `cc_crm_nomicon.db`, nie Produktion). Den Login im Code zu entfernen wurde bewusst abgelehnt (Merge-Konflikte, Sicherheitsrisiko).

## Entscheidungen (Kurzfassung, Details in `ENTSCHEIDUNGEN.md`)

- **2026-10-14 (Auftrag Nutzer):** Ansichten Direct/Ueberlassung/Gesamt, gemeinsamer Kandidatenstatus, zwei lokale Demo-Logins - siehe `docs/ANSICHTEN.md` (Regeln, Route-zu-Ansicht, Schutzmassnahmen). Offene Rueckfragen dort (Kanzleiname bei fremden Prozessen, Uebernahme-Fee-Staffel, Lohnkosten-Annahme, Standardansichten, Einwilligung AÜ).

- **2026-10-12 (Nutzer):** Hermes und Nomicon sind gleichberechtigt und getrennt gebaut, nicht Kopie/Nachzuegler; es wird immer verglichen (`scripts/vergleich.py`, `docs/VERGLEICH.md`). Offen: Wasserzeichen VERTRAULICH im DOCX-Export (V-002).

- **2026-10-05 (Nutzer):** `short_profile` bleibt aus der MCP-Ausgabe, zuschaltbar per `CC_CRM_AI_INCLUDE_PROFILE` (Standard aus). DSGVO-Umfang: Anonymisierung leert zusaetzlich `cv_extraction_raw`, Stationen, aktuellen Arbeitgeber, Examensnoten, Gehalt und Kuendigungsfrist; Einwilligungsnachweis (Datum, Quelle, Pseudonym `candidate_number`, `anonymized_at`) bleibt, das Flag `consent_received` faellt auf false; Lebenslauf-Bytes endgueltig fehlgeschlagener Scan-Jobs werden sofort geloescht.
- **2026-10-05 (Nutzer):** Vorstellungs-Archiv: bei jeder tatsaechlich versendeten Vorstellung (Mail mit Kandidat UND Kanzlei) wird der Versand unveraenderlich archiviert, nur Admins sehen ihn (404 sonst), kein Backfill; Entfernen nur nach Fristablauf, mit Antrag und zweitem Admin (Umsetzung durch Claude: eigene Antragstabelle statt der allen lesbaren Freigabe-Inbox).

- Kandidaten und Kanzleien = gemeinsamer Pool; **Prozesse und alles daran owner-gescopt** (`process_owner_scope`), Kommentare fuer alle sichtbar. Fremd = **404** (nie 403). Rollen `member` / `team_lead` / `admin`.
- Teamleiter sehen in Kalender, Team-KPIs und Analytics ihr Team; Live-KPI-Ranking bleibt fuer alle sichtbar; Kanzlei-Freigabeanfragen fuer alle lesbar.
- Freigabe-Inbox (neue Kanzlei, Honorar-Aenderung, Rechnung stellen); Prozess-Sharing additiv ("Geteilt mit"), Empfaenger darf nicht weiterteilen.
- Mandanten: kein Mandantenmodell; zweite Firma = eigene Kopie. Groessenordnung bis ca. 200.000 Kandidaten / 50+ Nutzer.
- Sequenzen nur mit Einwilligung (`consent_received`). Claude-Schnittstelle (MCP) standardmaessig AUS, nur lesen plus Vorschlaege mit Freigabe, Kommunikation sendet immer ein Mensch; MCP-Schluessel (`scope=mcp`) gelten nur fuer `/api/v1/mcp`.
- Microsoft-Login: nur bestehende aktive Nutzer, nie automatisch anlegen, SSO ohne 2FA.
- Prozesse ohne Owner sind fuer Nicht-Admins unsichtbar (Teamleiter: ihr Team, Admin: alle); neue Prozesse brauchen einen Owner (Service erzwingt es), Admin sieht Altfaelle unter `/prozesse/ohne-verantwortlichen` und weist zu.
- Microsoft-Login bindet beim ersten Login die unveraenderliche Kennung (`users.ms_oid`), lehnt Gaeste ab und bleibt bei Multi-Tenant-Konfiguration (`common` usw.) deaktiviert; Admin kann die Bindung loesen.

## Stolperfallen

- **Windows/lokal:** `python` ist der Store-Platzhalter und haengt - immer `backend/.venv/Scripts/python.exe`; pnpm per `corepack pnpm`. Viele Dateien haben CRLF - Skript-Edits muessen das beachten.
- **CI weicht von lokal ab** (Python 3.12, andere mypy-/SQLAlchemy-Typen): nach jedem Push `gh run list` pruefen.
- **Tests:** keine festen Datumswerte; Test-Payloads muessen gueltig sein (422 macht Tests wirkungslos); zuerst pruefen, dass das Setup Treffer erzeugt; `client`-Fixture legt eine `AuthSession` an; gleichnamige Testdateien in `tests/api` und `tests/services` kollidieren.
- **Neue Routen mit `submission_id`/`placement_id`/`fee_id`** brauchen `SubmissionAccess`/`PlacementAccess`/`FeeAccess` (erzwingt `tests/api/test_access_guard.py`).
- **Migrationen:** auf einer Kopie der lokalen DB upgrade, downgrade, upgrade; genau ein Head (aktuell siehe `CLAUDE.md`).
- **FastAPI 0.141:** `app.routes` enthaelt nur ein `_IncludedRouter`-Objekt, keine einzelnen Routen - fuer Routen-Pruefungen `app.openapi()` oder Verhaltenstests nutzen.
- **Buttons ignorieren Tailwind-Schrift:** `globals.css` setzt `button,input,select,textarea{font:inherit}` ohne Layer; `text-[..]`/`font-*` an `<button>` braucht `!` (z. B. `text-xs!`) oder ein Kind-Element.
- **Frontend:** nie `pnpm build`, waehrend `pnpm dev` laeuft (beide nutzen `.next`); dann Dev-Server stoppen, `.next` loeschen, neu starten.
- Harmlose Git-Meldung `failed to delete '.git/worktrees/charming-mendeleev-84844e'` ignorieren. Nie ins Repo: Projekt in OneDrive, Zugangsdaten, `.git-korrupt-backup/`, `backend/data/lukas_postfach_import/`, `backend/scripts/full_dry_run_log.txt`.
