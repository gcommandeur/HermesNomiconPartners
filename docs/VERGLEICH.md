<!-- pruefstand hermes=72f02ab nomicon=3d048d7 -->
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

## Geschichte des Pruefstands

- 2026-10-12: Umstellung von „Kopie mit Upstream-Merge" auf „getrennt und gleichberechtigt". Gemeinsame Basis `0225fb6`.
