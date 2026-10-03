# Hermes im Vergleich: was fehlt zur Skalierung, was ist wirklich neu

Stand: 2026-10-03 (Cloud-Sitzung). Auftrag: gezielt mit `margince/margince` vergleichen und sich
andere CRMs ansehen, um zu erkennen, was neu ist und was technisch sicher, schnell und
**nicht zu kompliziert** ist.

## So wurde verglichen (und was nicht)

- **Margince:** das Repository (Commit `223994f`, flacher Klon) gelesen: README, `docs/explanation/`
  (Architektur, Schreib-Rückgrat, Job-Flotte, Suche, Custom Fields, Webhooks, Autorisierung,
  Frontend), `docs/reference/performance-budgets.md`, `go.mod`, `package.json`. **Nichts davon
  wurde gestartet oder ausgeführt**, es ist ein Lese-Vergleich. Margince ist laut README noch nicht
  veröffentlicht ("coming autumn 2026"), Lizenz BUSL-1.1.
- **Andere CRMs:** nur Websuche, keine eigenen Tests. Belegt sind Twenty, Attio, Bullhorn und der
  Markt der Recruiting-CRMs (Loxo, Manatal, Recruit CRM, Zoho Recruit). **Salesforce habe ich nicht
  gesondert recherchiert.**
- Aussagen über Hermes stammen aus unserem Code (Stand `entwicklung`).

## Was Margince ist (und warum man es nicht nachbauen sollte)

Go-Backend (19 Module, drei Prozess-Rollen), Postgres 16 + Redis 7, React/Vite-Frontend, OpenAPI als
Vertrag, von einem Unternehmen mit ca. 250 Ingenieuren gebaut. Sehr viel davon ist **Prozess und
Schutzgeländer** (Architektur-Linter, ADRs, Gates), das für ein Team in unserer Größe zu schwer wäre.
Lehrreich sind die einzelnen Bausteine, nicht das Ganze.

| Baustein bei Margince | Idee | Für Hermes sinnvoll? |
|---|---|---|
| Job-Queue in Postgres (River), Jobs vorab deklariert, ein Zeilen-Job pro Mandant | Hintergrundarbeit überlebt Deploys, Wiederholung und Fehler sind sichtbar, **kein Redis nötig** | Ja, in klein |
| Transaktionaler Outbox: Änderung + Audit-Zeile + Event in **einer** Transaktion | Kein "gespeichert, aber Event verloren"; Grundlage für Webhooks/Benachrichtigungen | Ja, in klein |
| Audit-Log append-only per DB-Trigger, App-Rolle hat nur SELECT/INSERT | Manipulationssicher gegen die laufende Software | Ja, sehr billig |
| Suche: Postgres-Volltext (`tsvector`, GIN) + Vektoren (pgvector), Fusion per RRF, Zeilenrechte **in** der Abfrage | Gute Treffer ohne eigenen Suchdienst | Teilweise (Volltext ja, Vektoren später) |
| Custom Fields als **echte typisierte Spalten** über eine einzige gesicherte DDL-Stelle | Ehrliches SQL für Auswertungen | Nein in dieser Form; JSONB ist einfacher |
| Ausgehende Webhooks (Standard Webhooks, signiert, Retry, Dead-Letter, Replay) | Integrationen ohne Polling | Ja, wenn externe Systeme kommen |
| Agent-Oberfläche über MCP, jede Aktion protokolliert, Tageslimit, Freigaben nicht für Agenten | Claude/Copilot arbeiten **im** CRM, mit den Rechten des Nutzers | Ja als Idee, zuerst nur lesend |
| Veröffentlichte Performance-Budgets mit letzter Messung (Record öffnen < 100 ms, Suche < 200 ms) | Leistung ist messbar statt gefühlt | Ja, sehr billig |
| API-Typen aus dem OpenAPI-Vertrag generiert | Frontend und Backend können nicht auseinanderlaufen | Ja, billig |
| Eine Firma pro Installation, **keine** `tenant_id`, kein Row-Level-Security | Einfach | Gleiche Entscheidung wie bei uns |

Das letzte ist wichtig: Auch Margince baut **kein** Mehrmandantensystem. Meine frühere Aussage, ein
fehlendes Mandantenmodell sei eine Skalierungslücke, gilt nur, wenn Hermes als Dienst für fremde
Firmen angeboten werden soll.

## Andere CRMs, kurz

- **Twenty** (Open Source): NestJS + Postgres + Redis, **BullMQ-Worker** für Hintergrundjobs, GraphQL
  und REST, Webhooks; Custom-Objekte und -Felder per Oberfläche aus Metadaten, ohne Migration.
  Quelle: [Twenty bei Railway](https://railway.com/deploy/twenty-crm-self-hosted-server-worker-wired-right-updated-sep26--twenty-crm-self-hosted),
  [Marmelab-Vergleich 2026](https://marmelab.com/blog/2026/01/09/open-source-crm-benchmark-2026).
- **Attio:** frei definierbare Objekte/Felder/Beziehungen, E-Mail und Kalender werden in Echtzeit
  eingespielt; Nachteil laut Tests: ohne Vorarbeit am Datenmodell kaum nützlich.
  Quelle: [Attio-Review](https://lightfield.app/blog/attio-review).
- **Bullhorn:** REST-API mit OAuth 2.0; Ereignisse nur per **Polling-Abo mit 7 Tagen Ablauf, keine
  Push-Webhooks**. Quelle: [Bullhorn-API](https://pipeline.zoominfo.com/sales/bullhorn-api),
  [Apideck](https://www.apideck.com/integrations/bullhorn-ats.md). Gilt als Altsystem gegenüber
  KI-nativen Wettbewerbern.
- **Loxo / Manatal / Recruit CRM:** KI als Kern (Kandidaten-Scoring, Matching, Sourcing,
  Mehrkanal-Outreach), Preise ab ca. 15 $ pro Nutzer und Monat bei Manatal.
  Quelle: [Manatal-Vergleich](https://www.manatal.com/blog/bullhorn-alternatives),
  [JazzHR-Vergleich](https://www.jazzhr.com/insights/bullhorn-alternatives).

**Was daraus neu ist (Trend):** (1) das CRM füllt sich aus Mail/Kalender selbst, (2) KI-Matching und
-Outreach sind Standard, (3) Agenten dürfen kontrolliert **im** System handeln, (4) Datenmodell
anpassbar ohne Entwickler, (5) Ereignisse/Webhooks statt Polling.
Hermes hat (1) teilweise (Mail-Sync mit Auto-Kandidat), (2) teilweise (Matching, Profil-Generator,
Sequenzen), (3) nicht, (4) nicht, (5) nicht.

## Was Hermes technisch fehlt (geprüft gegen unseren Code)

Korrektur zu meiner ersten Antwort: Für Namen, E-Mail und Berufsbezeichnung der Kandidaten sowie
Kanzlei- und Kontaktnamen **existieren** bereits Trigram-Indizes (Migration `7c1e651c4844`); `ILIKE`
ist dort also indexgestützt. Nicht abgedeckt sind Stadt/PLZ, die Rollen-Textsuche, Zusammenfassung
und CV-Inhalte, und es gibt weder Ranking noch semantische Suche.

| # | Lücke | Beleg im Code | Einfachste wirksame Lösung | Aufwand |
|---|---|---|---|---|
| 1 | Kein Fehler-/Leistungs-Monitoring | keine Sentry/OpenTelemetry/Prometheus-Abhängigkeit, nur `/health` | Sentry + strukturierte Logs mit Request-ID + `/readyz` | klein |
| 2 | Kein Test gegen Postgres, obwohl produktiv Postgres | Tests nur SQLite; `alembic check` meldet Altlast-Drift (`job_mandates`, `mail_accounts`, `mail_messages`, `users`) | CI-Job mit Postgres-Service-Container, Migrations-Rundlauf, "genau ein Head"-Test | klein |
| 3 | Hintergrundarbeit in Threads | `threading.Thread` in `auth.py`, `sourcing.py`, `candidates.py` | Postgres-Queue (`SELECT … FOR UPDATE SKIP LOCKED` oder `procrastinate`/`pgqueuer`), kein Redis | mittel |
| 4 | Kein Ereignis-Mechanismus | `integrations/webhooks/` ist leer | Outbox-Tabelle, in derselben Transaktion wie Audit schreiben; Grundlage für Webhooks | mittel |
| 5 | Audit-Log nicht manipulationssicher | App kann `audit_logs` ändern/löschen | Trigger verbietet UPDATE/DELETE; App-Rolle nur INSERT/SELECT | klein |
| 6 | Cockpit rechnet im Speicher | `CockpitService.build` lädt Prozesse/Offers/Placements/Fees und filtert in Python | Aggregation in SQL (`GROUP BY`), Zeitraum und Besitzer als WHERE | mittel |
| 7 | Frontend-Typen von Hand | `frontend/src/lib/api/types.ts` (>1200 Zeilen) | `openapi-typescript` aus dem FastAPI-OpenAPI erzeugen, CI prüft Drift | klein |
| 8 | Suche ohne Ranking/Semantik | siehe Korrektur oben | `tsvector` + GIN für CV/Zusammenfassung/Rollen, später pgvector fürs Matching | mittel |
| 9 | Keine Leistungsziele | nirgends gemessen | 4 Budgets (Kandidat öffnen, Liste, Suche, Speichern) + Messskript mit 50.000 Testkandidaten | klein |
| 10 | Datenmodell nur per Migration änderbar | rund 43 feste Kandidatenfelder | `custom` als JSONB + Katalogtabelle (Typ, Label, Auswahlwerte), GIN-Index | mittel |
| 11 | Keine Agenten-/Integrationsfläche | API-Keys vorhanden, kein MCP/Webhook | zuerst MCP **nur lesend** über bestehende Rechte, jede Anfrage im Audit | mittel |
| 12 | Mail-Abruf per Polling | Graph-Delta alle 5 Minuten | Graph-Change-Notifications später; Polling reicht bis dahin | später |

## Bewusst nicht übernehmen

Redis, Go-Neubau, Microservices, ein Metadaten-Engine à la Twenty, Build-Zeit-Erweiterungen und
Architektur-Linter wie bei Margince. Jedes davon löst ein Problem, das wir mit Postgres und
FastAPI-Bordmitteln (noch) nicht haben, und erhöht die Betriebslast.

## Vorgeschlagene Reihenfolge (jeweils ein eigener Schritt auf `entwicklung`)

1. **Sicherheitsnetz:** #2 Postgres in der CI, #1 Sentry/Logs, #9 Messskript. *Erst messen, dann bauen.*
2. **Billige Härtung:** #5 Audit append-only, #7 generierte API-Typen.
3. **Skalierung der Auswertung:** #6 Cockpit in SQL, #8 Volltextsuche.
4. **Zuverlässigkeit:** #3 Queue, #4 Outbox, danach Webhooks.
5. **Produkt:** #10 Custom Fields (JSONB), #11 MCP lesend.

## Nicht geklärt

- Ob Hermes je für **fremde Firmen** angeboten werden soll (dann Mandantenmodell, sonst nicht).
- Erwartete Größenordnung (Nutzer, Kandidaten, Mails pro Tag): ohne Zahl bleibt "Skalierung" ein
  Gefühl. Schritt 1 (Messen) liefert die Grundlage.
- Salesforce und die genannten Recruiting-CRMs wurden nur über Dritt-Webseiten betrachtet.
