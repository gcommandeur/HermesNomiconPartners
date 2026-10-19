<!-- pruefstand hermes=db26014 nomicon=24c2d3f -->
# Vergleich Hermes CRM <-> Nomicon Partners

Beide Repos sind **gleichberechtigt und getrennt**: kein Merge, kein Upstream, eigene Migrationsketten.
Was zusammengehoert, wird bewusst verglichen und von Hand uebernommen (Cherry-Pick/Patch), mit Grund.

**Ablauf** (Sitzungsbeginn und vor jedem Push): `python scripts/vergleich.py --hermes <Pfad zum Hermes-Klon>`
→ jede neue Abweichung unten eintragen → `--update-pruefstand`. Fehlerkorrekturen und Sicherheitsfixes
aus dem anderen Repo werden grundsaetzlich uebernommen, Features nach Absprache mit dem Nutzer.
Uebernommene Migrationen bekommen im Zielrepo eine eigene neue Revision (Ketten sind getrennt).

Status: **uebernehmen** · **uebernommen** · **bewusst anders** · **offen** (Nutzer fragen)

## Register

| Nr | Thema | Hermes | Nomicon | Status / Grund |
|----|-------|--------|---------|----------------|
| V-001 | Kalender: Outlook-Termin ohne Betreff liess Terminliste mit 500 ausfallen | `5e578de` | uebernommen (Patch inkl. Test, OpenAPI neu) | **uebernommen** (Bugfix) |
| V-002 | DOCX-Profil-Export: Wasserzeichen VERTRAULICH | `14c9c64` entfernt (Wunsch Hermes-Nutzer) | entfernt per Patch (Nutzer 2026-10-14), Test angepasst | **uebernommen** |
| V-003 | OpenAPI-Schema neu erzeugt | `3fe2872` (nach Kalender-Fix) | `71e969f` (pydantic 2.14, Decimal-Muster) | **bewusst anders**: jedes Repo erzeugt das Schema aus eigenem Code neu |
| V-004 | Firmenschicht (Name, Logo, Navy/Poppins-Design, Mailvorlagen) | Hermes-Design | Nomicon-Design (`brand-theme.css`, `public/brand`, `backend/templates/anonymes_profil_master.docx` mit Nomicon-Logo, Navy `#001C4A`) | **bewusst anders**: zwei Marken. Profil-Briefkopf (DOCX) seit 2026-10-14 Nomicon statt Commandeur |
| V-005 | Arbeitnehmerueberlassung (Einsaetze, Stundenzettel, Kundenfreigabe, Abrechnung) | nicht vorhanden | `staffing_*`, `/ueberlassung`, Migrationen `nomicon01staff`, `nomicon02invoices` | **bewusst anders**: Geschaeftsmodell nur Nomicon; Hermes kann es bei Bedarf uebernehmen |
| V-006 | Provisionsmodell (Quartalsbericht, nur Admin) | nicht vorhanden | `commission_*`, Migration `nomicon03commission` | **bewusst anders**: nur Nomicon |
| V-007 | Firmen-Reste in der Oberflaeche (`document-panel.tsx` nutzt `brand.companyName`, Platzhalter in `postfaecher/page.tsx`) | feste Texte | Platzhalter/Brand-Variable | **offen** – Kandidat fuer Hermes (neutral, schadet nicht) |
| V-008 | Eingriffe in gemeinsame Dateien: `api/v1/router.py`, `models/__init__.py`, `services/approvals.py` (`staffing_invoice`), `seed_data.py --staffing`, `middleware.ts`, `conditional-shell.tsx`, `navigation.ts`, Kandidaten-Detailseite, Geschaeftsfuehrung-Seite | ohne | mit Nomicon-Zweigen | **bewusst anders**; bei Aenderungen in diesen Dateien auf Hermes-Seite pruefen |
| V-009 | Alembic-Ketten | Head `g3b5d7f9a1c2` | Head `nomicon03commission` (Kette ab `g3b5d7f9a1c2`) | **bewusst anders**: getrennt; keine Merge-Heads |
| V-010 | CSV-Export: Formel-Injektion (Zellen mit `=`, `+`, `-`, `@`) | `5e10283` (Paket C3) | `80b090c`, Funktion in `lib/csv-safe.ts` + Test | **uebernommen** (Sicherheit) |
| V-011 | Sicherheitsmeldungen: `pypdf` 6.19, `cryptography` 50.0.2 | `ad16891` | `24c2d3f` (pyproject; lokal pypdf 6.21.1, cryptography 50.0.2, Suite gruen) | **uebernommen** (Sicherheit) |
| V-012 | Frontend-Abhaengigkeiten mit bekannten Luecken: `next` ^15.5.27, `vitest` ^4.1.11 | `4b0676a` | nicht uebernommen | **uebernehmen, offen**: braucht `pnpm install` (neuer `pnpm-lock.yaml`, `node_modules` ersetzt) und stoert laufende Dev-Server; Nomicon hat eigenes Vitest-Setup (Node-Umgebung, nur `lib/*.test.ts`). Vorschlag: einmal ohne laufende Server und mit Build/Vitest pruefen |
| V-013 | Fee-Pflicht ab Interview (`expected_fee` Pflicht beim Wechsel nach interview/offer/placement, Dialog, Anzeige „Fee offen", Vorschlag aus Kanzlei-Prozentsatz) | `47cdd32` (Paket A, 32 Dateien, Hermes-Prompt `claude_code_prompt_fee_pflicht_ab_interview`) | **nicht vorhanden** (`STATUSES_REQUIRING_CLIENT` nur fuer die Kunden-Pflicht) | **offen** (Nutzer entscheidet): Fuer Direct in Nomicon sinnvoll (gleiche Pipeline, Fee-Spalten und Summen sind in Nomicon schon da), betrifft aber `submissions.py`, `submission-views.tsx`, OpenAPI und Demo-Daten, die beide Repos geaendert haben. Nur Direct, Ueberlassung unberuehrt. Nicht uebernommen |
| V-014 | Fee-Anzeige: erfundene Werte entfernt, UI-Summen wie Backend | `a6b23d8` (Paket B) | nicht uebernommen | **offen**: haengt an V-013 (`lib/fee.ts`); mit V-013 zusammen entscheiden |
| V-015 | DSGVO: Einwilligung zurueckziehen als Markierung, Loeschantrag fuer alle Mitarbeiter, zweistufige Anonymisierung (Migration `h4c6e8a0b2d3`) | `7dbaab2`, `953f0c7`, `5941f2f` | nicht vorhanden | **offen** (Feature, Nutzer fragen): betrifft `candidates.py`, Loeschanfragen-Seite und braucht eine eigene Nomicon-Migration; Ueberlassungs-Besonderheit beim Loeschen (Aufbewahrung, Profil `RESTRICT`) muss mitbedacht werden |
| V-016 | Refactorings ohne Verhaltensaenderung (`recruiting.py`, `candidates.py`, `cv_extraction*.py`, `submission-views`, `candidates-table`, `postfaecher/page`) | `c520738`, `80aa46f`, `6cc2c37`, `cf8356d`, `c8bd69f`, `022ff5e` | nicht uebernommen | **bewusst anders**: reine Umbauten; in Nomicon sind dieselben Dateien an mehreren Stellen veraendert (Kandidatenliste/Filter, Ueberlassung), Uebernahme erzeugte Konflikte ohne Nutzen. Bei Bedarf spaeter |
| V-017 | Tests und Werkzeuge: 109 Frontend-Tests (jsdom, Testing Library), Playwright-Rauchtests als CI-Job, `restore_check.py`, CI-Trigger/Budget, Doku (`DEPLOYMENT.md`) | `b7b6c3b`, `3dcee6c`, `219d4ab`, `0f1122c`, `030a47a`, `db26014` | nicht uebernommen | **offen/bewusst anders**: Nomicon nutzt Vitest ohne jsdom; CI-Aenderungen (`.github/workflows/ci.yml`) und `restore_check.py` nur nach Absprache, weil sie Push-Verhalten bzw. den Betrieb betreffen |
| V-018 | Tests fuer „Prozesse ohne Verantwortlichen" | `8ace04c` (Paket C4, nur Tests) | nicht uebernommen | **offen**: kein Fehler, nur zusaetzliche Tests; Nomicon hat die Seite im Test `owner_filter` abgedeckt |

## Geschichte des Pruefstands

- 2026-10-12: Umstellung von „Kopie mit Upstream-Merge" auf „getrennt und gleichberechtigt". Gemeinsame Basis `0225fb6`.
- 2026-10-19: Abgleich gegen Hermes `db26014` (29 neue Commits seit `72f02ab`, Hermes lesend in einem Temp-Klon). Fixes uebernommen (V-010, V-011), alles andere aufgelistet (V-012 bis V-018) und dem Nutzer zur Entscheidung gelassen. Hermes unveraendert.
