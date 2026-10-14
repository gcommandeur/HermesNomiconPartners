# Ansichten (Direct, Überlassung, Gesamt) - nur Nomicon

Alle Nutzer arbeiten in derselben Datenbank. Kandidaten und Kanzleien sind ein gemeinsamer Pool.
Ansichten sind eine **Berechtigungs- und Oberflächenebene** darüber:

| Ansicht | Schlüssel | Inhalt |
|---|---|---|
| Direct (Vermittlung) | `direct` | Prozesse, Vakanzen, Sourcing, Fee |
| Überlassung (AÜ) | `staffing` | Einsätze, Leiharbeitnehmer, Fristen, Stundenzettel, Abrechnung, Compliance |
| Gesamt (Geschäftsführung) | `management` | Rohertrag, Prognose, Provisionsmodell - **nur Admins** |

Die **Rolle** (`member`/`team_lead`/`admin`) regelt weiter, *welche Datensätze* man sieht
(`process_owner_scope`, `staffing_owner_scope`); die **Ansicht** regelt, *welche Module*. Lohn und
Marge sehen nur Admins, unabhängig von jeder Ansicht.

## Regeln (Server erzwingt sie)

- Admins haben immer alle drei Ansichten; ein Entzug wird abgelehnt (422).
- `management` ist nur für Admins vergebbar (422 sonst). Eine trotzdem in der Datenbank stehende
  Zeile wirkt für Nicht-Admins nicht.
- Mindestens eine Ansicht muss freigeschaltet bleiben; die Startansicht muss freigeschaltet sein.
- Nutzer ohne jede Freigabe-Zeile (nie konfiguriert) bekommen den **einstellbaren Standard**
  (`app_settings.views_default_for_new_users`, ohne Eintrag: nur Direct).
- Die Migration gibt allen aktiven Nutzern `direct`, Admins zusätzlich `staffing` und `management`.
- Gesperrtes Modul: **HTTP 403** mit „Diese Ansicht ist für dein Konto nicht freigeschaltet.“
  (kein Verstecken per 404). ID-Routen behalten das 404 für fremde Datensätze.
- Jede Änderung steht im Audit-Log (`entity_type=user_view_access`, Aktion `views_changed` bzw.
  `default_views_changed`, `changed_by` = Admin).
- Tabellen: `user_view_access`, `user_view_settings` (neue Tabellen, keine Spalte an `users`).

## Route → Ansicht

Durchgesetzt in `api/v1/router.py` (markiert `# NOMICON`) über `api/view_dependencies.py`.
`tests/api/test_access_views.py` ruft **jede** so zugeordnete Operation aus dem OpenAPI-Schema ohne
die Ansicht auf und erwartet 403 - eine neue Route unter diesen Präfixen ist automatisch geprüft.

| Ansicht | Routen (unter `/api/v1`) |
|---|---|
| `direct` | `/submissions/**`, `/vacancies/**`, `/sourcing/**`, `/feedback`, `/interviews`, `/offers`, `/placements/**`, `/fees` (Router `recruiting`), dazu `/placements/{id}/fees` und `/fees/{id}/invoice-status` (Router `approvals`) |
| `staffing` | `/staffing/**` (nicht `/public/timesheets/**`: Kundenfreigabe per Token, ohne Login) |
| `management` | `/commission/**`, `/management/**` (Rohertrag, Prognose, Alarme) |
| offen für jeden Angemeldeten | Kandidaten, Kanzleien, Kontakte, Kalender, Mailing, Postfächer, Notizen, Aufgaben, Freigaben (Inbox), Cockpit, KPI, `/me/**`, `/engagement/**`, `/clients/{id}/business` (Abschnitte folgen den Ansichten), Einstellungen |

## API

- `GET /me/views` - eigene Ansichten und Startansicht; `PUT /me/view` merkt die gewählte Ansicht.
- Admin: `GET /admin/view-access` (Matrix), `GET/PUT /admin/users/{id}/views`,
  `GET/PUT /admin/view-access/defaults` (Standard für nie konfigurierte Nutzer).

## Gemeinsamer Kandidatenstatus

Abgeleitet aus Prozessen und Einsätzen, nichts doppelt gespeichert (`services/engagement_status.py`).
Gesamtstatus: `frei`, `im_direct`, `im_einsatz`, `beides`, `vermittelt` (eine Vermittlung geht vor).
Zählt als „im Austausch“: Prozess in Quali Call bis Offer (nicht archiviert, nicht abgebrochen),
Vermittlung (Placement, auch archiviert), Einsatz geplant oder aktiv.

- **Sichtbarkeit (Standard, Rückfrage an den Nutzer):** Kanal, Stufe, zuständiger Mitarbeiter und
  Datum sieht jeder Angemeldete. Kanzleiname und IDs nur, wer Zugriff auf den Prozess/Einsatz hat
  (Owner-Scope, Freigabe, Admin); sonst `details_visible=false`, Kanzlei und ID leer. Lohn/Marge nie.
- **Offen für Direct / AÜ:** ja / nein / nicht geklärt (Standard), Tabelle `candidate_engagement_prefs`,
  jede Änderung im Audit-Log. Für AÜ kann eine eigene Einwilligung des Kandidaten nötig sein (Zweck der
  Verarbeitung) - offene Rechtsfrage, nicht entschieden.
- **Filter** der Kandidatenliste (`GET /candidates?engagement=`): `free_direct` (nicht im Direct-Prozess,
  nicht ausdrücklich „nein“), `free_staffing` (analog für Einsätze), `engaged` (irgendein Austausch).
- **Sammelabfrage** `POST /engagement/summary` (bis 500 Kandidaten, konstante Zahl von Abfragen, Test mit
  Abfragezähler); einzeln `GET /candidates/{id}/engagement`, `PATCH .../engagement-prefs`.
- **Konflikt beim Anlegen** (Prozess `POST /submissions`, Einsatz `POST /staffing/assignments`): „gebunden“
  heißt Vermittlung, anderer Kanal oder (gleicher Kanal) von einem Kollegen betreut - eigene parallele
  Prozesse bei anderen Kanzleien sind Alltag und lösen nichts aus. Modus **warnen** (Standard): 409 mit
  Hinweistext (nur die sichtbaren Angaben), erneut mit `?confirm_engagement=true`; Modus **sperren**:
  422, auch mit Bestätigung. Admin-Einstellung `GET/PUT /admin/engagement-settings`.

## Ansicht Direct (Ergänzungen)

- Kanban-Karte, Tabelle und mobile Liste zeigen die erwartete Fee. Ab Interview ist sie Pflicht; fehlt sie
  (Altfälle), steht **„Fee offen“** (gelb). Davor zeigt die Karte die alte Schätzung aus dem Gehaltswunsch,
  ausdrücklich mit `~` als Schätzung gekennzeichnet. Es wird kein Wert erfunden.
- Spaltenkopf: Σ der hinterlegten Fees, „gew.“ = Fee × Abschlusswahrscheinlichkeit (nur wo vorhanden), Zahl der
  Prozesse mit „Fee offen“.
- Kopfzeile: Pipeline-Wert (laufende Prozesse), erwartete Fees (gewichtet), überfällige Nachfassungen,
  laufende Gewährleistung. Rein im Frontend aus den geladenen Prozessen (`lib/fee-forecast.ts`).
- Hinweis: Die „Fee-Pflicht ab Interview“ aus Hermes ist in dieser Kopie nicht erzwungen (`expected_fee` ist
  nur ein optionales Feld); die Anzeige kommt damit zurecht.

## Ansicht Überlassung (Disposition)

`GET /staffing/disposition` (Sichtbereich wie überall, kein Lohn, keine Marge): aktive/geplante Einsätze,
offene Checklisten, **Bench** (aktive Leiharbeitnehmer ohne geplanten/aktiven Einsatz, „frei seit“ = Ende des
letzten Einsatzes, ersatzweise Eintritt), Stundenzettel-Eingang (offen, überfällig, beim Kunden,
freigegeben aber nicht abgerechnet, abgelehnt), Erlaubnis-Status. Die Seite `/ueberlassung` zeigt dazu das
Fristen-Radar und das **Einsatz-Board** (Anwärter/Onboarding, Geplant, Aktiv, Läuft aus = Ampel gelb/rot oder
Ende in 30 Tagen, Beendet der letzten 30 Tage). Lohn und Verrechnungssatz auf den Karten nur für Admins.

## Ansicht Gesamt (Geschäftsführung, nur Admins)

`GET /management/overview?period=week|month|quarter` (rollierend 7/30/90 Tage wie die KPI-Zeiträume):

- **Rohertrag** gestapelt: Direct = bezahlte Vermittlungshonorare (netto) im Zeitraum; Überlassung = Marge
  freigegebener Stunden = Stunden × (Verrechnungssatz − Stundenlohn × Arbeitgeber-Faktor).
- **Annahme (Rückfrage an den Nutzer):** der Arbeitgeber-Faktor ist der bereits einstellbare Faktor des
  Provisionsmodells (Standard 1,23). Es gibt keine Lohn-, Steuer- oder Sozialversicherungsberechnung.
- **Prognose:** Direct = erwartete Fee × Abschlusswahrscheinlichkeit laufender Prozesse (ohne Fee oder ohne
  Wahrscheinlichkeit fehlt ein Prozess in der Summe und wird gezählt); Überlassung = Marge je Stunde ×
  Wochenstunden × Restwochen aktiver Einsätze bis zum geplanten Ende, nie über die Höchstüberlassungsdauer hinaus.
- Kunden mit beiden Geschäften, Übernahme-Quote (Paare mit Einsatz und späterer Vermittlung desselben
  Kandidaten beim selben Kunden), Alarmleiste (Fristen rot/gelb, Erlaubnis, überfällige Rechnungen, Prozesse
  ohne Verantwortlichen). Das Provisionsmodell steht unverändert darunter.
- Rechenkern `services/management_calc.py` ist rein und gegen handgerechnete Beispiele getestet
  (`tests/services/test_management_calc.py`, `tests/api/test_management_overview.py`).
- Spaltenbezeichnungen der Team-Tabelle („Pitch/InMail“, „CV Sent“) bleiben: Pitch/InMail ist Stufe 1 der
  konsolidierten 7-Stufen-Pipeline, „CV Sent“ ist der Name der Stufe `cv_out` in der Timeline.

## Brücken

- **Übernahme durch den Kunden** (AÜ → Direct, am Einsatz): beendet den Einsatz und legt einen Prozess mit Fee
  an (war vorhanden). Neu: **Übernahme-Fee gestaffelt nach bisheriger Einsatzdauer** (Anteil am Honorarsatz des
  Kunden, einstellbare Tabelle unter Überlassung → Compliance, nur Admins). Startwerte sind **Platzhalter**:
  bis 3 Monate 100 %, bis 6 Monate 75 %, bis 9 Monate 50 %, bis 12 Monate 25 %, danach 0 %. Ein eigener Prozentsatz
  in der Übernahme-Maske überschreibt die Staffel. Vorschau: `GET /staffing/assignments/{id}/takeover-preview`.
- **Als Einsatz anbieten** (Direct → AÜ, am Kandidaten und an der Prozess-Karte): `POST /staffing/offer-from-candidate`
  legt das Leiharbeitnehmer-Profil (Anwärter) und, mit Kunde und Beginn, einen geplanten Einsatz an. Der
  Konflikt-Hinweis aus dem Kandidatenstatus greift.
- **Geschäft mit dieser Kanzlei** (`GET /clients/{id}/business`, Block auf der Kanzleiseite): Prozesse (Ansicht
  Direct), Einsätze und Fristen (Ansicht Überlassung), jeweils im eigenen Sichtbereich; Umsatz nur für Admins.

## Demo-Logins (nur lokal)

Zwei Klick-Anmeldungen ohne Passwort und ohne E-Mail-Code für Vorführung und Tests - ein **bewusstes Umgehen der
Anmeldung**, deshalb mehrfach abgesichert (`services/demo_login.py`, `tests/api/test_demo_login.py`):

1. Schalter `CC_CRM_DEMO_LOGIN` (Standard aus). Im Frontend zusätzlich `NEXT_PUBLIC_CC_CRM_DEMO_LOGIN=true` im
   Build; ohne ihn kommt der Code der Buttons im Build gar nicht vor.
2. Wirkt nur bei `CC_CRM_ENVIRONMENT` `local`, `test` oder `demo` UND SQLite oder Postgres auf localhost. In jeder
   anderen Umgebung (Produktion, DigitalOcean, fremder Datenbankhost) **startet die App nicht**, wenn der Schalter
   an ist (klare Fehlermeldung); in unsicherer Umgebung antwortet der Endpunkt außerdem mit 404.
3. `POST /auth/demo-login` mit `{"persona": "admin" | "vermittler"}` meldet ausschließlich `demo-admin@nomicon.local`
   und `demo-vermittler@nomicon.local` an (nie ein anderes Konto), überspringt dort die 2FA und teilt sich die
   Ratenbegrenzung mit dem normalen Login. Die Adressen enden auf `.local`: der normale Login-Weg (E-Mail-Prüfung)
   lehnt sie ab, und die Konten haben ein zufälliges, nie ausgegebenes Passwort.
4. Demo-Admin: Rolle `admin`, alle drei Ansichten, Startansicht Gesamt. Demo-Vermittler: Rolle `member`, nur Direct;
   der Demo-Admin kann ihm unter *Einstellungen → Administration → Ansichten* live Ansichten geben und entziehen.
5. Dazu eine dritte Person **Demo Kollegin** (`demo-kollegin@nomicon.local`, nicht anmeldbar) als Betreuerin
   „fremder“ Prozesse.

Start lokal: `cd backend && CC_CRM_DATABASE_URL=sqlite:///./cc_crm_nomicon.db alembic upgrade head`, dann
`python scripts/seed_data.py seed --clients 12 --candidates 40 --submissions 25 --staffing 8 --demo`. Backend:
`CC_CRM_DEMO_LOGIN=true CC_CRM_ENVIRONMENT=local uvicorn cc_crm.main:app --app-dir src --port 8000`, Frontend:
`NEXT_PUBLIC_CC_CRM_API_URL=http://localhost:8000/api/v1 NEXT_PUBLIC_CC_CRM_DEMO_LOGIN=true pnpm dev`. Auf der
Anmeldeseite erscheinen **Demo: Admin** und **Demo: Vermittler**.

Der Demo-Seed legt Kandidaten für alle Zustände an: frei für alles, nur AÜ offen, nur Direct offen, im Prozess des
Demo-Vermittlers, im Prozess der Kollegin (für den Demo-Vermittler ohne Kanzleiname), im AÜ-Einsatz, Direct und
AÜ gleichzeitig, vermittelt - plus Prozesse mit erwarteter Fee ab Interview.

## Offene Fragen

- Teamleiter sehen weiter die Team-Kennzahlen (`/team-kpis`, `/kpi-ranking`; Team-begrenzt). Die neue
  Ansicht „Gesamt“ ist nur für Admins. Soll die Geschäftsführungs-Seite für Teamleiter bleiben?
- Kanzleiname bei fremden Prozessen im Kandidatenstatus: Standard „nicht sichtbar“. Soll er für alle sichtbar sein?
- Konflikt-Definition (siehe oben) und Standardmodus „warnen“ passen so?
- Übernahme-Fee-Staffel: die Startwerte sind Platzhalter. Welche Staffel ist vertraglich vereinbart?
- Lohnkosten-Annahme für den Rohertrag der Überlassung (Arbeitgeber-Faktor des Provisionsmodells, Standard 1,23): passt das?
- Standardansichten für neue Mitarbeiter: bisher nur Direct (einstellbar).
- Einwilligung des Kandidaten für Überlassung (Zweck der Verarbeitung): rechtlich zu klären, nicht entschieden.
