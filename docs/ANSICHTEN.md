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
| `management` | `/commission/**` |
| offen für jeden Angemeldeten | Kandidaten, Kanzleien, Kontakte, Kalender, Mailing, Postfächer, Notizen, Aufgaben, Freigaben (Inbox), Cockpit, KPI, `/me/**`, Einstellungen |

## API

- `GET /me/views` - eigene Ansichten und Startansicht; `PUT /me/view` merkt die gewählte Ansicht.
- Admin: `GET /admin/view-access` (Matrix), `GET/PUT /admin/users/{id}/views`,
  `GET/PUT /admin/view-access/defaults` (Standard für nie konfigurierte Nutzer).

## Offene Fragen

- Teamleiter sehen weiter die Team-Kennzahlen (`/team-kpis`, `/kpi-ranking`; Team-begrenzt). Die neue
  Ansicht „Gesamt“ ist nur für Admins. Soll die Geschäftsführungs-Seite für Teamleiter bleiben?
