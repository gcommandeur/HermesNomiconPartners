# Plan: Skalierungs-Schritte 1-5

Stand: 2026-10-03 (Cloud-Sitzung). Grundlage: `docs/CRM_VERGLEICH_SKALIERUNG.md`.
**Status: Entwurf, wartet auf Freigabe des Nutzers.** Gebaut wird erst nach "passt".

Arbeitsweise wie immer: jeder Teilschritt ist ein eigener Commit auf `entwicklung`, mit Tests,
`ruff`/`mypy`/`pytest`/`lint`/`typecheck`/`build` grün, CI grün und Eintrag in
`docs/PROJEKT_STAND.md`. Nach `main` nur per Pull Request auf ausdrückliche Anweisung.
Aufwand grob: S = ein kurzer Block, M = ein halber Tag Sitzung, L = mehr.

---

## Schritt 1: Sicherheitsnetz (erst messen, dann bauen)

**1a. Postgres in der CI (S-M)**
- Neuer CI-Job `backend-postgres` mit Postgres-16-Service-Container.
- Migrationen von leer bis `head`, dann `downgrade -1` und wieder `upgrade` (der jeweils neueste Schritt).
- Test "genau ein Alembic-Head".
- `alembic check` gegen Postgres. Dafür zuerst die bekannte Altlast-Drift auflösen
  (`job_mandates.priority`, `mail_accounts.address`, `mail_messages.message_id`,
  `users.calendar_feed_token`). Vorgehen: pro Fall prüfen, ob Modell oder Migration recht hat;
  bevorzugt das **Modell** an den echten DB-Stand angleichen (keine Änderung an der Produktions-DB).
  Nur wo die DB wirklich falsch ist, eine Migration.
- Die komplette Testsuite zusätzlich gegen Postgres: `tests/conftest.py` bekommt einen optionalen
  Schalter `CC_CRM_TEST_DATABASE_URL`; mit Postgres wird das Schema einmal angelegt und nach jedem
  Test per `TRUNCATE` geleert (schnell). Ohne den Schalter bleibt alles wie heute (SQLite).
- Abnahme: CI-Job grün; ein absichtlich kaputter Migrationsschritt lässt ihn rot werden.

**1b. Monitoring ohne Pflicht-Konto (S)**
- Middleware: Request-ID (aus `X-Request-ID` oder neu), Dauer, Status, Nutzer-ID als eine
  JSON-Logzeile pro Request (DigitalOcean zeigt die Logs ohnehin).
- Langsame Requests (> 1 s) und langsame SQL-Abfragen (> 300 ms) als Warnung mit Request-ID.
- `/readyz` (DB erreichbar, Migrationsstand = head) zusätzlich zu `/health`.
- Sentry nur, wenn `CC_CRM_SENTRY_DSN` gesetzt ist (Abhängigkeit `sentry-sdk`); ohne DSN passiert nichts.
- Abnahme: Tests prüfen Log-Felder, Request-ID im Antwort-Header, `/readyz` bei kaputter DB = 503.

**1c. Messskript und Leistungsziele (S-M)**
- `backend/scripts/perf_bench.py`: legt in einer Wegwerf-DB 50.000 Kandidaten, 500 Kanzleien und
  5.000 Prozesse an, misst p50/p95 für: Kandidat öffnen, Liste (50, gefiltert), Suche, Speichern,
  Cockpit, Prozessliste.
- Ziele (wie bei Margince, angepasst): öffnen < 100 ms, Liste < 150 ms, Suche < 200 ms,
  Speichern < 150 ms, Cockpit < 500 ms (Server, p95).
- Ergebnis wird in `docs/PERFORMANCE.md` geschrieben (mit Rechner, Datum, DB). Nicht gemessenes wird
  als "nicht gemessen" aufgeführt, nicht weggelassen.
- Läuft im Postgres-CI-Job als **nicht blockierender** Schritt (nur Ausgabe), lokal auf Abruf.
- Ergebnis entscheidet, wie dringend Schritt 3 wirklich ist.

**1d. (Empfehlung, braucht dich) Migrationen nicht mehr beim App-Start**
- Heute läuft `alembic upgrade head` beim Start jeder Backend-Instanz (`core/migrations.py`). Bei
  zwei Instanzen gleichzeitig ist das riskant.
- Vorschlag: in DigitalOcean einen "Pre-Deploy Job" mit `alembic upgrade head` anlegen und den
  Start-Aufruf per Schalter abschalten. Code-Teil: Schalter `CC_CRM_MIGRATE_ON_STARTUP`
  (Standard an, damit nichts bricht). DO-Teil: von dir.

## Schritt 2: Billige Härtung

**2a. Audit-Log unveränderbar (S-M)**
- Migration: Postgres-Trigger auf `audit_logs`, der `UPDATE` und `DELETE` ablehnt.
- **Gefundene Lücke, die mitgelöst werden muss:** Kandidaten-Änderungen speichern alte und neue
  Werte (z. B. E-Mail, Telefon) im Audit-Log, und `anonymize()` entfernt diese **nicht**. Nach einer
  DSGVO-Löschung stehen die Daten also noch im Audit-Log. Lösung: genau eine erlaubte Ausnahme. Die
  Anonymisierung setzt in ihrer Transaktion ein Flag (`SET LOCAL cc_crm.audit_redaction = 'on'`), und
  der Trigger erlaubt dann nur das Schwärzen von `old_values`/`new_values` dieses Kandidaten
  (Werte werden zu `"[entfernt]"`), nie das Löschen der Zeile.
- Grenze (ehrlich dokumentiert): schützt gegen die laufende Software, nicht gegen jemanden mit den
  DB-Eigentümer-Zugangsdaten. Eine eigene App-Rolle ohne UPDATE/DELETE-Recht wäre der nächste Schritt,
  setzt aber 1d voraus (Migrationen brauchen mehr Rechte als die App).
- SQLite (Tests) hat keinen solchen Trigger. Deshalb laufen diese Tests im Postgres-Job aus 1a.

**2b. API-Typen aus dem Backend erzeugen (M)**
- `backend/scripts/export_openapi.py` schreibt das OpenAPI-Schema (ohne laufenden Server, auch wenn
  `/openapi.json` in Produktion abgeschaltet bleibt).
- Frontend: `openapi-typescript` erzeugt `src/lib/api/schema.d.ts`. CI prüft, dass die Datei aktuell
  ist (sonst rot).
- Die handgeschriebenen Typen in `types.ts` werden für die Kern-Entitäten (Kandidat, Kanzlei, Kontakt,
  Prozess, Aufgabe, Nutzer, Placement, Fee) auf die erzeugten Typen umgestellt. Jede Abweichung, die
  `tsc` dabei findet, ist ein echter Fehler und wird behoben oder gemeldet. Der Rest folgt nach und nach.

## Schritt 3: Auswertung und Suche in die Datenbank

**3a. Cockpit in SQL (M-L)**
- Zuerst ein Vergleichstest: ein umfangreicher Testdatensatz, die **alte** Berechnung liefert das
  erwartete Ergebnis. Erst dann umbauen. Die neue Berechnung muss exakt dasselbe liefern.
- `CockpitService.build` und `_recruiting_kpis` laden heute alle Prozesse, Offers, Placements und Fees
  und filtern in Python. Neu: Zählungen und Summen per `GROUP BY`/`WHERE` in der Datenbank, Listen
  (heiße Prozesse, Datenlücken, Aufgaben) mit Limit.
- Abnahme: Vergleichstest grün, Messskript aus 1c zeigt den Unterschied.

**3b. Volltextsuche (M)**
- Postgres: generierte `tsvector`-Spalte auf `candidates` (Name, Berufsbezeichnung, Zusammenfassung,
  Rollen, Stadt) mit GIN-Index, deutsche Wortstämme plus `unaccent` ("Muller" findet "Müller").
  Ergebnis nach Relevanz sortiert (`ts_rank`). Zusätzlich Trigram-Index für Stadt/PLZ.
- SQLite bleibt beim heutigen `LIKE`-Verhalten (gleiche Treffer für einfache Suchen), damit die
  lokale Entwicklung unverändert läuft. Die Postgres-Variante wird im Postgres-Job getestet.
- Semantische Suche (pgvector) ist **nicht** Teil dieses Schritts.

## Schritt 4: Zuverlässige Hintergrundarbeit und Ereignisse

**4a. Job-Warteschlange in Postgres (M)**
- Eigene kleine Tabelle `jobs` (Art, Daten, Status, Versuche, `run_after`, `locked_until`, letzter
  Fehler). Abholen per `FOR UPDATE SKIP LOCKED`, Wiederholung mit wachsendem Abstand, nach N
  Versuchen "failed". Ein abgestürzter Worker gibt den Job nach `locked_until` frei.
- Bewusst ohne Redis und ohne Bibliothek (Alternative wäre `procrastinate`; eigene Tabelle ist kleiner,
  läuft auch unter SQLite in den Tests und bleibt lesbar).
- Worker: `backend/scripts/run_worker.py` als dauerlaufender Prozess.
- Umgezogen werden: CV-Extraktion, Sourcing-Läufe (heute `BackgroundTasks` im Webprozess) und die
  Sicherheitsalarm-Mails (heute `threading.Thread`). Der 2FA-Code bleibt synchron (er muss sofort raus).
- Admin-Ansicht: fehlgeschlagene Jobs sehen und neu anstoßen.
- **Braucht dich:** eine DigitalOcean-"Worker"-Komponente (kleinste Größe).

**4b. Ereignis-Tabelle (Outbox) (S-M)**
- Jeder Audit-Eintrag erzeugt in **derselben Transaktion** eine Zeile in `event_outbox`
  (`entity_type.action`, z. B. `candidate_submission.status_changed`). Ein Mechanismus, kein zweiter
  Weg, der vergessen werden kann.
- Der Worker aus 4a verteilt die Ereignisse an die Webhooks (4c).

**4c. Ausgehende Webhooks (M)**
- Admin legt unter Einstellungen Ziele an (nur `https`, keine privaten/internen Adressen gegen SSRF),
  wählt Ereignisarten, bekommt ein Signatur-Geheimnis einmal angezeigt (verschlüsselt gespeichert wie
  die Postfach-Passwörter).
- Versand nach dem Standard-Webhooks-Format (Header `webhook-id`, `webhook-timestamp`,
  `webhook-signature`), Wiederholung, danach "tot", Wiederholen per Knopf, Zustellprotokoll.
- **Datenschutz-Vorschlag:** Nutzlast nur mit IDs und Ereignisart, keine Personendaten. Der Empfänger
  holt Details per API-Key.

## Schritt 5: Produkt-Erweiterungen

**5a. Eigene Felder (M-L)**
- Tabelle `custom_field_definitions` (Objekt, Schlüssel, Bezeichnung, Typ: Text/Zahl/Datum/Ja-Nein/
  Auswahl, Auswahlwerte, Reihenfolge, aktiv) und eine JSONB-Spalte `custom_fields` an Kandidat,
  Kanzlei und Kontakt (GIN-Index unter Postgres).
- Werte werden gegen die Definition geprüft (Typ, Auswahlwerte). Änderungen landen automatisch im
  Audit-Log.
- Admin-Seite zum Anlegen. Die Felder erscheinen im Bearbeiten-Dialog und auf der Detailseite. Ein
  Filter "Feld = Wert" in der Kandidatenliste für Auswahl- und Ja/Nein-Felder.
- Bewusst **keine** echten DB-Spalten wie bei Margince (das bräuchte zur Laufzeit `ALTER TABLE`).

**5b. Lesende Claude-Schnittstelle (MCP) (M)**
- MCP-Endpunkt unter `/api/v1/mcp` (offizielles Python-SDK). Anmeldung mit dem bestehenden API-Key,
  der an einen Nutzer gebunden ist. Es gelten **genau dessen** Rechte (`process_owner_scope`,
  Freigaben).
- Nur lesende Werkzeuge: Kandidaten suchen/öffnen, eigene Prozesse, fällige Aufgaben, Cockpit-
  Kurzfassung, Kanzlei suchen/öffnen.
- Jeder Aufruf wird im Audit-Log festgehalten (wer, welches Werkzeug, wann). Es gibt ein Tageslimit
  pro Schlüssel. Schreibende Werkzeuge kommen nicht in diesem Schritt.
- **Braucht dich:** Datenschutz-Entscheidung (siehe unten).

---

## Was du entscheiden oder tun musst

| # | Frage / Aufgabe | Mein Vorschlag |
|---|---|---|
| E1 | Sentry-Konto (EU-Region) anlegen und DSN als Variable setzen, oder vorerst nur Logs? | Erst nur Logs; Sentry ist vorbereitet |
| E2 | DO-Pre-Deploy-Job für Migrationen (1d) | Ja |
| E3 | DO-Worker-Komponente für die Warteschlange (4a), kleine monatliche Kosten | Ja |
| E4 | Webhook-Nutzlast nur mit IDs | Ja |
| E5 | Für welche Objekte eigene Felder? | Kandidat, Kanzlei, Kontakt (nicht Prozess) |
| E6 | MCP: dürfen Kandidatendaten an Claude gehen (Auftragsverarbeitung mit Anthropic)? | Erst klären, dann bauen; bis dahin 5b zurückstellen |
| E7 | Audit-Schwärzung bei Anonymisierung (2a) als einzige Ausnahme vom "unveränderbar" | Ja (DSGVO-Pflicht) |

## Reihenfolge und Abhängigkeiten

1a → 1b → 1c → (1d mit dir) → 2a (braucht 1a für die Tests) → 2b → 3a → 3b (beide mit 1c gemessen)
→ 4a → 4b → 4c → 5a → 5b (nach E6).

Jeder Teilschritt ist einzeln nutzbar. Ein Stopp nach jedem beliebigen Teilschritt hinterlässt keinen
halben Zustand.
