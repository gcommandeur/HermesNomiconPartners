# Hermes - gemeinsamer Projektstand

Diese Datei ist die **gemeinsame Gedaechtnisstuetze** aller Claude-Sitzungen (Laptop und Cloud/Handy). Sitzungen sehen die Gespraeche der jeweils anderen nicht - nur das, was hier und im Repository steht.

## Pflicht bei JEDER Aufgabe

1. **Vor dem Start lesen:** diese Datei und `CLAUDE.md`. Dann `git fetch` und `origin/main` einbeziehen (die andere Seite hat evtl. weitergearbeitet).
2. **Am Ende aktualisieren, im selben Commit wie die Aufgabe:**
   - einen Eintrag oben im **Protokoll** (neueste zuerst): Datum, wer (`Laptop` oder `Cloud`), was, Commits/Branch, was nicht geprueft wurde;
   - **Offene Punkte** pflegen (Erledigtes entfernen, Neues ergaenzen);
   - neue **Entscheidungen** und **Stolperfallen** festhalten, sobald sie anfallen.
3. Nichts Geheimes eintragen (keine Passwoerter, Tokens, Verbindungs-Strings, Kunden-/Kandidatendaten).
4. Eine Aufgabe ist erst fertig, wenn Tests/Pruefungen gruen sind, die **CI bei GitHub gruen** ist und diese Datei stimmt.

## Wer arbeitet wie

| | Laptop-Sitzung | Cloud-Sitzung (Handy) |
|---|---|---|
| Umgebung | Windows, `backend/.venv`, `corepack pnpm` | Linux, Start-Hook installiert Pakete |
| Git | direkt auf `main` (siehe `CLAUDE.md` > Workflow) | eigener Branch `claude/...`, Pull Request, Merge durch den Nutzer |
| Nur hier moeglich | Produktions-Skripte, DigitalOcean, Klicktests mit Login | - |

Der Nutzer will langfristig alles vom Handy aus erledigen koennen. `main` deployt automatisch nach DigitalOcean.

## Offene Punkte (nach Prioritaet)

1. **Neue Cloud-Sitzung pruefen:** startet der Hook, sind Pakete installiert, laufen `pytest`/`ruff`/`mypy` ohne Rueckfrage, wird `docs/PROJEKT_STAND.md` gelesen? Falls nicht, Einstellungen/Hook nachbessern.
2. **Prozess-Sharing (Cloud-Branch `claude/funny-allen-ayl3bi`)**: Backend + Frontend fertig, CI auf dem Branch gruen, aber **noch nicht gemergt und nicht von der Laptop-Sitzung inhaltlich geprueft**. Migration `d2f5a8b1c6e4` haengt an `c9a1d4e7f2b3`. Vor dem Merge: Diff pruefen, `alembic heads` = 1.
3. **Schutzregel fuer `main`** bei GitHub (Checks `backend` und `frontend` Pflicht). Entscheidung noetig, weil sie auch den direkten Push der Laptop-Sitzung betreffen kann.
4. **Vom Nutzer selbst auszufuehren** (nie von Claude): die drei Produktions-Skripte in `backend/scripts/` (`cleanup_service_users.py`, `backfill_cv_in_recorded_at.py`, `backfill_cv_available_from_documents.py`, alle standardmaessig Dry-Run) und das Zuruecksetzen des DigitalOcean-`doadmin`-Passworts (stand einmal in einer Diagnose-Datei im Klartext).
5. **Nicht live im Browser geprueft:** Teamleiter-Nutzerverwaltung, Freigabe-Inbox und Rechnungsbereich, Sourcing-Umkreissuche mit echtem Lauf, Kandidaten-Timeline, Prozess-Zugriffssperren mit echten Logins. Alles ist nur ueber Tests/Build abgesichert.
6. **Entscheidungen offen:** Kalender und KPI-Ranking haben eigenes Admin-Scoping (Teamleiter sieht dort nur Eigenes); Analytics erlaubt Nicht-Admins die Auswahl anderer Nutzer im Filter; Kanzlei-Freigabeanfragen (`approval-requests/for/client_company`) sind fuer alle lesbar.
7. **Daten:** Prozesse ohne `owner_user_id` (aus der Zeit vor dem Feld) sind fuer Nicht-Admins unsichtbar - ggf. Owner nachtragen.
8. **CI-Ausbau:** Postgres-Migrationstest (produktiv Postgres, Tests nur SQLite), Pruefung auf genau EINEN Alembic-Head, optional Browser-Tests (Playwright, Demo-Modus).
9. **Weiterbauen auf Team/Sharing:** Notifications, Sequenzen.
10. **Kleinigkeiten:** Quick-Log auf Kandidat mit offenem Kollegen-Prozess fuehrt dessen Prozess weiter (Grenzfall, bewusst); Aktivitaet "Prozess angelegt" hat keinen Autor.

## Entscheidungen (mit Grund)

- **Kandidaten und Kanzleien = gemeinsamer Agentur-Pool**, ohne Owner-Scoping (jeder muss den ganzen Bestand durchsuchen koennen). **Prozesse und alles daran** sind owner-gescopt. **Kommentare** (Notizen, Feedback) sind fuer alle sichtbar.
- **Fremd = 404, nicht 403** (verraet die Existenz nicht); fremd und nicht existent sind ununterscheidbar.
- **Rollen:** `member` / `team_lead` / `admin`; Teamleiter einstufig ueber `users.manager_id`. `process_owner_scope(user, session)` liefert immer `None` (Admin) oder eine Liste von IDs. Rolle nur im Code validiert, kein DB-CHECK.
- **Freigaben:** Nicht-Admin-Aktionen "neue Kanzlei", "Honorar-Aenderung", "Rechnung stellen" gehen ueber die Inbox. Neue Kanzlei wird sofort angelegt (`approval_pending`), bei Ablehnung **gesperrt statt geloescht**. Honorar: alte Werte gelten bis zur Freigabe. Den Rechnungs-Schritt (Entwurf, Gestellt, Faellig, Bezahlt) gab es nicht und wurde dafuer mitgebaut.
- **Audit/Timeline:** normale Edits als `updated` mit alt/neu; Autor bei Notizen als FK (`created_by_user_id`), bei Feedback als E-Mail-Text (kleinere Aenderung). Kommentar-Endpunkt auf Kandidaten-Ebene, weil Feedback an gescopten Prozessen haengt, Kommentare aber fuer alle sichtbar sein sollen.
- **Geo/Umkreissuche:** nur PLZ-/Stadt-genaue Koordinaten (`precise`), der grobe PLZ-Zonen-Fallback zaehlt wie "nicht aufloesbar"; kein Kartenversatz in Distanzberechnungen; Index einmal laden statt Abfrage pro Kandidat. Sourcing-Umkreis max. 50 km, laeuft im Hintergrund mit Fortschritt/Stopp.
- **Performance:** Kandidaten-Detailseite laedt nur die Prozesse/Kanzleien dieses Kandidaten (vorher alle, ~10 s, jetzt unter 1 s).
- **URL-Zustand der Kandidatenliste:** Filter/Suche/Sortierung/Seite in der URL; `back`-Parameter fuer den Rueckweg; Topbar liest `window.location` statt `useSearchParams`, sonst bricht das statische Prerendering der ganzen App.
- **`.claude/settings.json`:** erlaubt Pruefbefehle und das Pushen von `claude/*`; Force-Push, `reset --hard`, `branch -D` gesperrt. **Keine** Sperre fuer Pushes auf `main`, weil Verbote lokal nicht uebersteuerbar sind und den Laptop-Workflow blockieren wuerden.

## Stolperfallen

- **Windows/lokal:** `python` ist der Store-Platzhalter und haengt - immer `backend/.venv/Scripts/python.exe`; pnpm per `corepack pnpm`. Viele Dateien haben CRLF-Zeilenenden - Skript-Edits muessen das beachten (das Edit-Werkzeug erledigt das).
- **CI weicht von lokal ab** (Python 3.12 und andere mypy-/SQLAlchemy-Typen): ein lokal gruener Lauf garantiert keine gruene CI. Nach jedem Push `gh run list` pruefen.
- **Tests:** keine festen Datumswerte (Zeitbomben); Test-Payloads muessen gueltig sein - ein ungueltiger (422) macht den Test wirkungslos (kam zweimal vor); zuerst pruefen, dass das Setup ueberhaupt Treffer erzeugt.
- **Neue Routen mit `submission_id`/`placement_id`/`fee_id` im Pfad** brauchen `SubmissionAccess`/`PlacementAccess`/`FeeAccess`.
- **Migrationen** immer auf einer Kopie der lokalen DB upgrade, downgrade, upgrade testen. Aktueller Head auf `main`: `c9a1d4e7f2b3`.
- **Harmlose Git-Meldung:** `failed to delete '.git/worktrees/charming-mendeleev-84844e'` (toter Worktree-Eintrag auf dem alten OneDrive-Pfad) - ignorieren.
- **Verbotene Pfade/Orte:** Projekt nie zurueck in einen OneDrive-Ordner; nie Zugangsdaten committen; Ordner `.git-korrupt-backup/`, `backend/data/lukas_postfach_import/`, `backend/scripts/full_dry_run_log.txt` gehoeren nicht ins Repo.

## Protokoll (neueste zuerst)

- **2026-10-03 Laptop** - Einstellungen fuer die Arbeit vom Handy (`.claude/settings.json`, Start-Hook `.claude/hooks/cloud-setup.sh`, `.gitattributes`, CLAUDE.md-Abschnitt) und diese Datei ueber Pull Request #2 nach `main` gemergt (CI gruen, per Rebase: `89bef29`, `f655b43`). Noch nicht in einer echten Cloud-Sitzung geprueft.
- **2026-10-02 Cloud** - Prozess-Sharing ("Geteilt mit"): `29b5f9a`, `5c234aa`, `1547028` auf `claude/funny-allen-ayl3bi`; Freigaben nur durch Eigentuemer/Teamleiter/Admin, Rechnungs-Endpunkte beruecksichtigen Freigaben; CI auf dem Branch gruen. Nicht gemergt.
- **2026-10-02 Laptop** - Rolle `team_lead` (`2cd6c1f`), CI-Fix mypy-Typen (`5fa2180`), Rechnungs-Endpunkte nur fuer Eigentuemer/Admins (`3ba25b5`), Kandidaten-Timeline mit Autoren (`b424b40`), Prozesse per ID gesperrt (`3590392`), CLAUDE.md-Einfuehrung (`283430e`), alte Branches aufgeraeumt.
- **2026-10-01 Laptop** - Owner-Scoping der Prozess-Listen (`3e2f16e`), Freigabe-Inbox (`7bb21fe`), klickbare KPI-Kacheln (`c501541`), Audit-Trail fuer Edits (`583b84b`), Sourcing-Umkreissuche (`005391c`), Rueckweg/Profil-Performance (`debfaed`, `b09cd5b`).
- **2026-09-30 Laptop** - Recruiter-Rechte im Cockpit, Topbar-Anzeige, Cache-Reset beim Nutzerwechsel (`a01a50e`); CV-In-Analytics und Dokument-Upload (`eba8bca`, `5f42509`); Umkreissuche-Praezision, Wiesbaden-Regression, N+1-Performance (`8965a92`, `5256710`); KPI-Punkte/Geschaeftsfuehrung/Live-Ranking.
- **davor** - Geo-Mapping, PLZ-Koordinaten (`a4d7a2d`, `6858732`), CV-Out-Kampagne (`d36b5d2`).
