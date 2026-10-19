# Arbeitnehmerüberlassung (AÜG) — Nomicon-Modul

Nur in der Nomicon-Kopie (nicht in Hermes). Gebaut in der merge-schonenden Bauweise aus `KOPIE.md`
(neue Dateien, markierte Eingriffe `NOMICON`, Tabellen mit Präfix `staffing_`).

> **Kein Rechtsrat.** Alle gesetzlichen Werte (Höchstdauer, Equal Pay, Unterbrechung) sind
> einstellbare Annahmen und müssen mit Fachanwalt oder Verband bestätigt werden. Tarifverträge
> (z. B. Branchenzuschläge) können abweichen. Das gilt auch für die Oberfläche; dort steht derselbe
> Hinweis.

## Zweck und Abgrenzung

Das Modul verwaltet Leiharbeitnehmer, Überlassungsverträge, Einsätze, die Pflicht-Checkliste je
Einsatz, die Erlaubnis nach AÜG, die Fristen (Höchstüberlassungsdauer, Equal Pay) und — in den
späteren Paketen — Stundenzettel und Abrechnung.

**Bewusst nicht gebaut: die Lohnabrechnung.** Das System berechnet **keine Löhne, Steuern oder
Sozialabgaben**. Der Stundenlohn ist ein Stammdatum; für die Lohnabrechnung gibt es später nur einen
CSV-Export (Stunden je Leiharbeitnehmer und Zeitraum) für Steuerberater oder Lohnsoftware.

## Datenmodell

Ein Leiharbeitnehmer ist ein **bestehender `Candidate`** mit zusätzlichem Profil — der
Kandidatenpool bleibt gemeinsam (Kandidaten sind agenturweit sichtbar, nur das Überlassungsprofil
und die Einsätze folgen eigenen Regeln).

| Tabelle | Inhalt |
|---|---|
| `staffing_workers` | 1:1 zu `candidates`; Status (In Auswahl [intern `applicant`], aktiv, ruhend, ausgeschieden), Eintritt/Austritt, Stundenlohn, Entgeltgruppe, Wochenstunden, Arbeitserlaubnis gültig bis, Notizen |
| `staffing_contracts` | Überlassungs-/Rahmenvertrag je Kunde: Nummer, gültig von/bis, Branche (Branchenzuschlag), Dokument, Status |
| `staffing_assignments` | Einsatz: Leiharbeitnehmer, Kunde, Vertrag, Disponent (`owner_user_id`), Beginn, geplantes/tatsächliches Ende, Ort, Tätigkeit, Verrechnungssatz, Lohn, Status (geplant, aktiv, beendet, abgebrochen) |
| `staffing_assignments` (Ergänzung, Migration `nomicon08equalpay`) | zusätzlich `equal_pay_confirmed_on` und `equal_pay_confirmed_by_user_id`: der Disponent hat den Lohn bei Equal Pay geprüft und angeglichen (siehe „Equal Pay mit Folge“) |
| `staffing_assignment_checklist_items` | sechs Pflichtpunkte je Einsatz (Arbeitsvertrag/Nachweis § 11, Merkblatt, Überlassungsvertrag § 12, Konkretisierung, Sicherheitsunterweisung, PSA-Protokoll) mit erledigt/Datum/Dokument |
| `staffing_prior_periods` | **Vorzeiten beim Kunden** (Migration `nomicon07prior`): früher geleistete Überlassungszeiten desselben Leiharbeitnehmers beim selben Kunden (anderer Verleiher, vor CRM-Start, sonstiges) mit Beginn, Ende, Herkunft, Notiz |
| `staffing_licenses` | Erlaubnis nach AÜG: Behörde, Aktenzeichen, gültig von/bis (leer = unbefristet), Dokument, Erinnerungsvorlauf in Tagen |
| `staffing_timesheets`, `staffing_timesheet_entries` | Stundenzettel je Einsatz und Zeitraum (Paket G); Freigabe-Token nur als Hash |

Abweichung von der Aufgabenbeschreibung: Tabellen heißen durchgehend `staffing_…` (auch
`staffing_assignments` statt `assignments`), damit spätere Hermes-Tabellen nicht kollidieren.
Geld ist `Numeric(8,2)` (Stundensätze); im API-Schema kommt es wie die übrigen Geldfelder als Text
(`"14.50"`). Änderungen werden im Audit-Log (`audit_logs`, `entity_type` mit Präfix `staffing_`)
festgehalten.

Hinweis zum Löschen: Ein Kandidat mit Überlassungsprofil kann nicht gelöscht werden (Fremdschlüssel
`RESTRICT`) — er lässt sich anonymisieren; ein anonymisierter Kandidat kann aber kein neues
Überlassungsprofil bekommen. Das Verhalten beim DSGVO-Löschen von Leiharbeitnehmern (Aufbewahrungsfristen
für Lohn- und Überlassungsunterlagen) ist **nicht geklärt** (siehe offene Fragen).

## Fristen (`services/staffing_deadlines.py`)

Reine Funktionen ohne Datenbank und ohne Uhr, mit eigener Testsuite (`tests/services/test_staffing_deadlines.py`).

**Einstellbare Werte** (Standard, `DeadlineConfig`; gespeichert in `app_settings`, Admin-Oberfläche
unter *Überlassung → Compliance*):

| Wert | Standard | Bedeutung |
|---|---|---|
| Höchstüberlassungsdauer | 18 Monate | je Paar (Leiharbeitnehmer, Kunde) |
| Equal Pay | nach 9 Monaten | gilt ab dem Folgetag |
| Unterbrechung | 3 Monate | **länger** als dieser Wert setzt den Zähler zurück; genau 3 Monate zählen noch zusammen |
| Ampel gelb | unter 60 Tagen Restlaufzeit | |
| Ampel rot | unter 30 Tagen oder überschritten | |

**Rechenmodell.** Gezählt werden Einsatztage; ineinanderliegende oder unmittelbar aufeinanderfolgende
Einsätze werden vereinigt, **Lücken zählen nicht mit**. „N Monate“ sind die Kalendertage von
Kettenbeginn bis `add_months(Beginn, N)`. Ohne Lücke endet die Höchstdauer am Tag vor
`add_months(Beginn, 18)`; jede Lücke (bis 3 Monate) verschiebt sie um ihre Länge nach hinten.
Monatsarithmetik schneidet am Monatsende ab (31.8. + 6 Monate = 29.2./28.2.). Ein offener Einsatz
läuft bis heute; nach dem letzten bekannten Ende wird ununterbrochene Fortsetzung angenommen
(Projektion der Frist). Liegt der letzte Einsatz länger als die Unterbrechungsgrenze zurück, gibt es
keinen fortsetzbaren Zähler mehr; ein neuer Einsatz beginnt bei null.

Beispiele (Standardwerte): Beginn 1.1.2025, ohne Lücke → Equal Pay ab 1.10.2025, Höchstdauer bis
30.6.2026. Einsatz 1.1.–31.3.2025, nächster ab 1.7.2025 (Lücke genau 3 Monate) → Zähler läuft weiter,
Höchstdauer bis 29.9.2026; nächster ab 2.7.2025 → Zähler beginnt neu.

**Vorzeiten beim Kunden (seit 2026-10-17, Annahme, kein Rechtsrat).** Zeiten früherer Überlassungen an
denselben Entleiher zählen vollständig mit, auch bei einem anderen Verleiher oder vor dem CRM-Start.
Sie werden je Leiharbeitnehmer erfasst (Leiharbeitnehmer-Detail und Kandidaten-Reiter „Überlassung“,
Abschnitt „Vorzeiten beim Kunden“; API `GET|POST /staffing/workers/{id}/prior-periods`,
`PATCH|DELETE /staffing/prior-periods/{id}`; Löschen ist als Eingabekorrektur erlaubt und steht im
Audit-Log). Eine Vorzeit ist **immer abgeschlossen** (Ende ≥ Beginn, Ende nicht in der Zukunft) und
trägt keinen Lohn. Der Rechenkern nimmt sie als zusätzliche Zeiträume (`compute_deadline(...,
prior_spans=...)`): Vereinigung und Reset-Regel wie bei Einsätzen (Lücke bis 3 Monate verbindet, länger
setzt zurück – auch zwischen Vorzeit und Einsatz); `prior_days` nennt die Tage der Kette, die **nur**
aus Vorzeiten stammen („inkl. 10 Monate Vorzeit“ in der Fristanzeige). Das Equal-Pay-Datum rückt
dadurch nach vorn. Vorzeiten eines anderen Kunden zählen nicht. Die Vorzeiten gehören zum
Leiharbeitnehmer (gemeinsamer Pool wie die Person), nicht zu einem Einsatz; Rechte wie die übrigen
Überlassungs-Routen. Beim Anlegen eines Einsatzes weist die Maske darauf hin, Vorzeiten zuerst zu
erfassen (Hinweis, kein Zwang).

**Überfällige Einsätze (seit 2026-10-17).** Ein **aktiver** Einsatz, dessen geplantes Ende vorbei ist,
zählt in der Fristrechnung als **offen** (Ende „offen“), bis er beendet oder verlängert wird — die
vorsichtige Richtung (Restlaufzeit kürzer, die Kette erlischt nicht, nur weil niemand das Ende pflegt).
Die reine Funktion bleibt rein; nur die Zuordnung `assignment_span(assignment, heute)` kennt „heute“.
Der tägliche Job legt am Tag nach dem geplanten Ende eine **Aufgabe mit hoher Priorität** für den
Disponenten an („Einsatz überfällig: … bei … — beenden oder verlängern“), einmalig je Einsatz **und**
geplantem Ende (wird das Ende verlängert und erneut überschritten, entsteht wieder eine). Die
Übersicht zeigt eine Warnzeile „N Einsätze überfällig“ mit Link auf die gefilterte Einsatzliste
(`/ueberlassung/einsaetze?ueberfaellig=1`, API `GET /assignments?overdue=true`); die Liste trägt das
Kennzeichen „Überfällig“ (`is_overdue`), die Aufgabenliste der Ansicht eine rote Aufgabe
`assignment_overdue`.

**Vorläufige Fristen (seit 2026-10-17).** `DeadlineResult.provisional` (und die API) ist wahr, wenn die
Kette einen **geplanten** (noch nicht aktivierten) Einsatz enthält oder ein Einsatz **ohne Enddatum**
zählt **oder** die Vorzeiten weder erfasst noch als „keine“ bestätigt sind; `provisional_reasons` nennt die
Gründe (`planned_assignment`, `open_end`, `prior_unconfirmed`). Die Oberfläche zeigt dann ein kleines
Kennzeichen „vorläufig“ mit Tooltip („Einsatz noch nicht aktiviert“ / „kein Enddatum erfasst“ / „Vorzeiten
nicht bestätigt“). Die **Ampelfarbe bleibt unverändert**.

**Bestätigung „Keine Vorzeiten“ (seit 2026-10-19, Migration `nomicon09priorconf`).** Tabelle
`staffing_prior_period_confirmations` (Leiharbeitnehmer, Kunde, `confirmed_on`, bestätigende Person, Notiz;
je Paar eindeutig). Mit Bestätigung **oder** erfassten Vorzeiten ist die Frist nicht mehr vorläufig; ohne
beides bleibt sie es („Vorzeiten nicht bestätigt“). API: `GET|POST /staffing/workers/{id}/prior-period-confirmations`
(wiederholtes Bestätigen aktualisiert; Datum nicht in der Zukunft, 422; bei bereits erfassten Vorzeiten 409),
`DELETE …/{client_id}` zum Zurücknehmen; Audit-Einträge `created`/`updated`/`deleted`. Rechte wie die
Vorzeiten selbst (gemeinsamer Pool wie die Person, unbekannte Person oder Kunde: 404). Oberfläche: im Reiter
„Überlassung“ am Kandidaten „Keine Vorzeiten bestätigen“ mit Datum und Person; „Zurücknehmen“.

**Equal Pay mit Folge (seit 2026-10-17, Annahme, kein Rechtsrat).** Ab dem Equal-Pay-Datum der Kette
legt der Job eine Aufgabe für den Disponenten an: „Equal Pay gilt ab TT.MM.JJJJ: Lohn von X bei Y prüfen
und angleichen“ — einmalig je Paar und Kette (Kennung `…:equal_pay:<Kettenbeginn>:<Nutzer>`).
**Erledigt**, sobald `equal_pay_confirmed_on` an einem Einsatz des Paares gesetzt ist: die Aufgabe wird
auf „erledigt“ gestellt und nicht neu erzeugt. Eine Bestätigung zählt nur für die **aktuelle Kette
und ab dem Stichtag** (Datum am oder nach `equal_pay_from`; nach einem Reset beginnt Equal Pay von vorn).
Bestätigen geht erst, wenn **heute ≥ Stichtag** des Paares ist (sonst 409 „Equal Pay gilt für dieses Paar
noch nicht … erst ab dem Stichtag möglich“); ein Bestätigungsdatum vor dem Stichtag wird ebenfalls
abgelehnt (409), weil es nicht zählen würde. **Vorwarnung:** 30
Tage vor dem Datum entsteht einmalig ein Hinweis („Equal Pay beginnt am …“, normale Priorität).
Bestätigen: `POST /assignments/{id}/equal-pay-confirmation` (optional `confirmed_on`, Standard heute;
nicht in der Zukunft, nicht vor Einsatzbeginn), zurücknehmen `DELETE` derselben Adresse (Eingabekorrektur);
beides mit Audit-Eintrag (`equal_pay_confirmed` / `equal_pay_unconfirmed`) und nur für geplante/aktive
Einsätze. Das Bestätigen darf **jeder mit Zugriff auf den Einsatz**; die **Lohnhöhe sehen und ändern
weiter nur Admins** — Aufgabentexte, Aufgabenliste und Antworten enthalten nur Namen und Datum, nie Lohn
oder Marge (per Test belegt, für Admin und Nicht-Admin). Oberfläche: Feld „Equal Pay — bestätigt am …“
mit Schaltfläche im Einsatz, am Leiharbeitnehmer und im Kandidaten-Reiter; in der Frist-Übersicht das
Kennzeichen „Equal Pay offen“.

**Täglicher Job** `scripts/run_staffing_deadlines.py` (`services/staffing_deadline_job.py`): legt
Aufgaben (`tasks`) an — an den Disponenten des Paares (ohne Disponent: an alle aktiven Admins) bei
gelb, rot, überschritten, Equal-Pay-Beginn (mit Vorwarnung) und überfälligen Einsätzen, und an die
Admins für ablaufende/abgelaufene Erlaubnisse. Je Paar und Stufe genau **eine** Aufgabe (Kennung in der Beschreibung), auch wenn sie
erledigt ist; ändert sich die Kette (neuer Beginn), kommen neue Aufgaben. Die Aufgaben erscheinen in
der Aufgabenliste und in der vorhandenen täglichen Fälligkeits-Mail.

## Aktivierungsregel

Statusfolge: geplant → aktiv | abgebrochen; aktiv → beendet | abgebrochen; beendet/abgebrochen sind
endgültig und nicht mehr änderbar. Ein Einsatz wird nur **aktiv**, wenn

1. eine gültige AÜG-Erlaubnis den Zeitraum abdeckt (Beginn bis geplantes Ende; ohne geplantes Ende bis
   heute — eine später ablaufende Erlaubnis meldet der tägliche Job) **und**
2. am Einsatz ein **Überlassungsvertrag** verknüpft ist, der den Zeitraum abdeckt (seit 2026-10-17, siehe
   unten) **und**
3. die Pflicht-Checkliste vollständig ist **und**
4. der Einsatz begonnen hat (Beginn ≤ heute, seit 2026-10-16; ein Einsatz in der Zukunft bleibt „geplant“).

Die Fehlermeldung nennt alle Probleme gemeinsam, z. B. „Keine gültige AÜG-Erlaubnis für den Zeitraum … Kein
Überlassungsvertrag am Einsatz verknüpft … Pflicht-Checkliste unvollständig (offen: Merkblatt …)“. Mit der ersten Aktivierung wird eine Person „In Auswahl“ automatisch zum
aktiven Leiharbeitnehmer. **Annahme:** Eine überschrittene Höchstdauer blockiert die Aktivierung
nicht; sie wird als rote Frist angezeigt und als Aufgabe gemeldet.

### Überschneidung desselben Leiharbeitnehmers (seit 2026-10-17, Entscheidung: nur warnen)

Beim Anlegen und beim Ändern von Beginn/Ende eines Einsatzes prüft `services/staffing_overlap.py`, ob für
**denselben** Leiharbeitnehmer ein anderer geplanter oder aktiver Einsatz (gleicher **oder** anderer Kunde)
im selben Zeitraum liegt (Zeiträume inklusive; angrenzende Tage überschneiden sich nicht; abgebrochene und
beendete Einsätze zählen nicht; ohne geplantes Ende läuft ein Einsatz offen; ein **aktiver** Einsatz mit
abgelaufenem geplantem Ende gilt wie im Fristen-Job als **offen**, bis er beendet oder verlängert wird — die eine
gemeinsame Regel steht in `services/staffing_open.py`: `is_overdue`, `effective_end_date`, `assignment_is_open`). Treffer: **409** mit der Meldung
„Überschneidung: …“ und der Liste `overlaps` (Einsatz-ID, Kunde, Beginn, geplantes Ende, Status — **ohne
Lohn und Verrechnungssatz**). Mit `confirm_overlap=true` (Einsatz anlegen, ändern, „Als Einsatz anbieten“)
wird trotzdem gespeichert und ein Audit-Eintrag `overlap_acknowledged` mit den überschneidenden Einsätzen
geschrieben. Eine bereits bestätigte Überschneidung fragt bei Änderungen ohne Datumsänderung nicht erneut.
Die Aktivierung sperrt **nicht**: `activation_problems` bleibt unverändert, der Einsatz-Detail liefert
zusätzlich `activation_warnings` (nur Hinweis). Die Oberfläche zeigt einen Bestätigungsdialog („Trotzdem
anlegen“ / „Trotzdem speichern“). Rechte und 404-Regeln sind unverändert.

### Überlassungsvertrag (§ 12 AÜG) als Aktivierungsvoraussetzung (seit 2026-10-17)

`services/staffing_contract_check.py` (reine Funktion). Der Vertrag **deckt** den Einsatz, wenn er (a) dem
Kunden des Einsatzes gehört, (b) den Status *aktiv* hat, (c) ein Gültig-ab hat, das nicht nach dem
Einsatzbeginn liegt (ohne Gültig-ab gilt er als nicht belegt – die Meldung sagt das), und (d) `valid_to`
leer ist oder nicht vor dem Ende des geprüften Zeitraums liegt. Der Zeitraum ist derselbe wie bei der
Erlaubnis: Beginn bis geplantes Ende, ohne Plan bis heute. Jede Verletzung hat eine eigene deutsche Meldung.

* Der Checklistenpunkt „Überlassungsvertrag“ wird **nicht mehr von Hand abgehakt**: er ergibt sich aus
  dieser Prüfung (Detailansicht und Zähler rechnen ihn live; der gespeicherte Haken wird bei jeder Änderung
  von Einsatz oder Vertrag und bei der Aktivierung nachgezogen). Ein manueller Versuch (abhaken oder
  zurücknehmen) liefert 422 mit Erklärung.
* **Bestehende Einsätze werden nicht rückwirkend verändert.** Die Regel greift bei der nächsten
  Aktivierung; bereits aktive Einsätze ohne Vertrag listet `backend/scripts/list_active_assignments_without_contract.py`
  (nur lesend, ohne Lohnwerte).
* Ändert sich Vertrag (Status, Gültigkeit) oder Einsatz (Vertrag, Beginn, geplantes Ende) eines **aktiven**
  Einsatzes so, dass der Vertrag den Zeitraum **nicht mehr** deckt, entsteht einmalig eine **Aufgabe** für den
  Disponenten (ohne Disponent: aktive Admins; Kennung `[staffing-contract:…]` mit dem Zustand von Vertrag und
  Zeitraum, nur der Übergang „gedeckt → nicht gedeckt“ löst aus). Die Änderung wird **nicht blockiert**; der
  Aufgabentext enthält keine Lohn- oder Margenwerte.
* Oberfläche: Im Einsatz steht die Pflichtauswahl „Überlassungsvertrag“ vor „Einsatz aktivieren“ (mit dem
  Grund, falls er den Zeitraum nicht deckt); die Checkliste zeigt den Punkt als „ergibt sich aus dem Vertrag“.

## Status eines Leiharbeitnehmers (eine Regel für Liste, Board, Fristen, Kennzahlen)

Festgelegt am 2026-10-16 nach einem Klick-Test (Person „aktiv seit“ in der Zukunft, aber im Board „In Auswahl“):

| Status | Bedeutung | Wie er entsteht |
|---|---|---|
| **In Auswahl** (früher „Anwärter“, interner Wert `applicant`) | ausgesucht bzw. für einen Kunden vorgesehen; noch kein Einsatz hat tatsächlich begonnen (auch mit geplantem Einsatz oder künftigem Eintritt) | Standard beim Anlegen; bleibt bis zur ersten Aktivierung eines Einsatzes |
| **Aktiv** | ab Eintritt bzw. Beginn des ersten Einsatzes, **nie in der Zukunft** | automatisch bei der ersten Einsatz-Aktivierung (Beginn ≤ heute); bleibt auch zwischen Einsätzen (dann „Bench“) |
| **Ruhend** | vorübergehend nicht einsetzbar | manuell |
| **Ausgeschieden** | Arbeitsverhältnis beendet | manuell (Austrittsdatum) |

Durchgesetzt in `services/staffing_workers.check_status_rule` (aktiv + Eintritt in der Zukunft → Fehler) und
`StaffingActivationService.activation_problems` (kein Aktivieren vor Beginn). Das **Einsatz-Board**
zeigt Personen „In Auswahl“ ohne geplanten/aktiven Einsatz als Personenkarte in der Spalte „In Auswahl“, Personen In Auswahl mit
geplantem Einsatz stehen über den Einsatz im Board (keine Doppelung). **Bench** = Aktive ohne geplanten/aktiven Einsatz
(Personen In Auswahl gehören nicht dazu). Die Liste zeigt bei Personen In Auswahl „Eintritt ab …“, bei allen anderen „seit …“.
Demo-Seed und `seed_demo` (zieht ältere Demo-Datenbanken nach) halten sich an die Regel.

## Überlassung am Kandidaten (seit 2026-10-16)

Alle Überlassungsinformationen zu einer Person stehen zusätzlich am Kandidaten (zweite Zugangsstufe zu denselben Daten,
keine zweite Datenhaltung): **Liste** `/kandidaten` mit Spalte „Überlassung“ (Status, bei Aktiv der Kunde, Warnsymbol mit
Resttagen bei gelber/roter Frist), Filter „Überlassung“ (nur Leiharbeitnehmer, Bench, Frist kritisch, In Auswahl) und einer
CSV-Spalte - alles nur mit der Ansicht Überlassung. **Detail** Reiter „Überlassung“: Stammdaten mit Bearbeiten (dasselbe
Formular wie unter Leiharbeitnehmer), „Als Leiharbeitnehmer anlegen“ (verknüpft den bestehenden Kandidaten; ein zweites
Profil gibt es nicht, 409), Einsätze mit „Neuer Einsatz“ (Leiharbeitnehmer vorausgefüllt), Fristen je Kunde mit Rechtshinweis,
Stundenzettel-Status mit Link zur Abrechnung, Bench-Hinweis „frei seit …“; Direct und Überlassung nebeneinander zeigt der
Kopfbereich der Kandidatenseite (gemeinsamer Kandidatenstatus mit Konflikt-Hinweis). Lohn und Marge sieht nur der Admin.

## Vereinfachung der Oberfläche (seit 2026-10-19)

* **Begriff:** „Anwärter“ heißt in der Oberfläche **„In Auswahl“** (interner Wert `applicant` unverändert; Board-Spalte
  „In Auswahl“). Vorschlag, nicht umgesetzt: „Geplant“ (Einsatz mit vollständiger Checkliste) und „In Auswahl“
  (ohne Einsatz oder Checkliste offen) könnten zusammengelegt werden.
* **Compliance im Hintergrund:** Menüpunkt und Seiten (Einstellungen, Erlaubnis, Übernahme-Staffeln) nur für **Admins
  und Teamleiter**; für alle anderen antwortet der Server mit 404 (`ComplianceAccess` in
  `api/staffing_dependencies.py`). Die Vermittler-Übersicht ist kompakt. Probleme erscheinen als **Meldungen**:
  Glocke oben rechts plus Aufgaben des Tagesjobs (u. a. „Überlassungsvertrag fehlt“,
  `[staffing-contract:…]`), **ohne Lohnwerte**. Ein Einsatz zeigt eine einzige Statuszeile, Details klappen auf.
* **Leiharbeitnehmer sind Kandidaten:** der Menüpunkt „Leiharbeitnehmer“ entfällt. In der Ansicht Überlassung führt
  „Kandidaten“ auf `/kandidaten?ueberlassung=workers`; Filter: Alle Leiharbeitnehmer, In Auswahl, Aktiv, Läuft aus,
  Bench (`active` neu im Backend). Die Überlassungsdaten stehen im Reiter „Überlassung“ am Kandidaten. Alte Adressen
  `/ueberlassung/leiharbeitnehmer` und `…/<id>` leiten dorthin weiter (unbekannte ID: zur Liste).

## Kanban auf der Übersicht (seit 2026-10-19)

Die Übersicht der Ansicht Überlassung zeigt für alle Rollen ein Kanban mit drei Spalten (`staffing-kanban.tsx`, Regeln in `lib/staffing-board.ts`): **In Auswahl** (geplante Einsätze und Personen „In Auswahl“ ohne Einsatz), **In Überlassung** (aktive Einsätze), **Überlassung endet bald** (aktiv, geplantes Ende in höchstens **6 Wochen** oder überfällig; füllt sich von selbst). Die ersten beiden Spalten bewegt man von Hand: Karte nach „In Überlassung“ ziehen oder „In Überlassung setzen“ (dieselbe Aktivierung wie im Einsatz; der Server prüft Checkliste, Vertrag, Erlaubnis und meldet, was fehlt). Personen ohne Einsatz haben „Einsatz anlegen“. Karte: Kandidat, Kunde, **Stundensatz (Verrechnungssatz) nur für Admins**. Zurück von „In Überlassung“ nach „In Auswahl“ gibt es nicht (kein erlaubter Statuswechsel); beendet wird im Einsatz. Das frühere 5-Spalten-Board ist ersetzt.

## Weitere Klarstellungen (seit 2026-10-19)

* **Hilfsfunktionen:** `create_task_once`, `active_admin_ids`, `pair_names` liegen jetzt in
  `services/staffing_task_helpers.py` (früher im Fristen-Job); Verhalten unverändert.
* **Überlassungsvertrag ohne „Gültig ab“ (offene Frage, nichts geändert):** Heute gilt ein solcher Vertrag als
  **nicht belegt** (`staffing_contract_check.supply_contract_problem`: „kein Gültig-ab hinterlegt“). Folge: ein
  geplanter Einsatz lässt sich nicht aktivieren (Aktivierungsfehler), und bei einem aktiven Einsatz entsteht
  die Meldung „Überlassungsvertrag … fehlt/deckt nicht“. Optionen: so lassen (blockieren) oder nur warnen.
  Entscheidung beim Nutzer.
* **Demo:** der Sonderfall „keine_vorzeiten“ hat ein bestätigtes „Keine Vorzeiten“ (nicht vorläufig); alle
  anderen Demo-Paare ohne Vorzeit zeigen „vorläufig – Vorzeiten nicht bestätigt“.

## Rechte

| | Mitarbeiter | Teamleiter | Admin |
|---|---|---|---|
| Einsätze (Liste, Detail, Checkliste, Statuswechsel) | eigene | eigene + Team | alle |
| Leiharbeitnehmer, Verträge, Fristenliste, Erlaubnis lesen | ja | ja | ja |
| Lohn und Verrechnungssatz **sehen und setzen** | nein (`null`/403) | nein | ja |
| Erlaubnis und Einstellungen **ändern** | nein | nein | ja |

* Sichtbarkeit der Einsätze folgt dem Disponenten (`owner_user_id`), wie bei Prozessen
  (`api/staffing_dependencies.py::staffing_owner_scope`). Fremd **und** nicht existent liefert dasselbe
  404. Einsätze ohne Disponent sind für Nicht-Admins unsichtbar. Ein Nicht-Admin darf nur Disponenten
  seines Bereichs zuweisen.
* Neue Routen mit `assignment_id` oder `timesheet_id` im Pfad **müssen** `AssignmentAccess` bzw.
  `TimesheetAccess` bekommen — erzwungen von `tests/api/test_staffing_access_guard.py`.
* Lohn/Marge erscheinen nirgends für Nicht-Admins: nicht in Listen, Details, Fristen-Übersicht; das
  Audit-Log (`/audit-logs`) ist Admin-only; die für alle lesbare Kandidaten-Historie enthält keine
  Überlassungs-Einträge (per Test belegt).

## Schnittstellen (`/api/v1/staffing`)

`GET /overview`, `GET /deadlines`, `GET|PUT /settings`; `GET|POST /workers`, `GET /workers/by-candidate/{id}`,
`GET|PATCH /workers/{id}`; `GET|POST /workers/{id}/prior-periods`, `PATCH|DELETE /prior-periods/{id}`;
`GET|POST /contracts`, `GET|PATCH /contracts/{id}`; `GET|POST /assignments`,
`GET|PATCH /assignments/{id}`, `POST /assignments/{id}/status`, `PATCH /assignments/{id}/checklist/{item}`;
`POST|DELETE /assignments/{id}/equal-pay-confirmation`, `GET /assignments?overdue=true`;
`GET|POST /licenses`, `PATCH /licenses/{id}`. Das OpenAPI-Schema (`/docs`) beschreibt Felder und Fehler.

## Stundenzettel und Kundenfreigabe

Pro Einsatz (aktiv oder beendet) und Zeitraum (höchstens 62 Tage, ohne Überlappung, im Einsatzzeitraum)
ein Stundenzettel mit Tageseinträgen (Stunden > 0 bis 24, Pause 0 bis 600 Minuten). Statusfolge:
offen → eingereicht → freigegeben | abgelehnt; ein abgelehnter Zettel wird beim Korrigieren wieder
offen (die Begründung bleibt im Audit-Log). Freigegebene Zettel sind endgültig. Die Oberfläche steht
im Einsatz-Detail unter „Stundenzettel“.

**Einreichen und Link.** „Einreichen“ erzeugt einen Freigabelink `…/stundenzettel/<token>`:

* Token: 256 Bit Zufall (`secrets.token_urlsafe(32)`), in der Datenbank **nur als SHA-256-Hash**; der Klartext
  steht nur in der Antwort des Einreichens (und wird einmal angezeigt).
* Gültig **14 Tage** (`TOKEN_VALID_DAYS`), **einmal nutzbar** (Freigabe oder Ablehnung verbraucht ihn), gilt nur
  für genau diesen Stundenzettel. „Link neu erzeugen“ ersetzt den alten Link.
* Ohne Login erreichbar: `GET /api/v1/public/timesheets/{token}`, `POST …/approve`, `POST …/reject`
  (Frontend: `/stundenzettel/<token>`, Weiterleitung `/api/stundenzettel/…`). Der Kunde sieht nur Name,
  Kunde, Zeitraum, Stunden — keine IDs, **kein Lohn, keine Marge**. Er gibt seinen Namen an; Ablehnen
  braucht eine Begründung.
* **Ratenbegrenzung** wie beim Login (`LoginRateLimiter`): 10 Fehlversuche je Client-IP in 10 Minuten, danach
  429, **bevor** der Token nachgeschlagen wird. Das Next-Frontend reicht dafür `CF-Connecting-IP` /
  `X-Forwarded-For` weiter (sonst teilten alle Kunden eine IP und eine Sperre).
* Die Client-IP stammt wie beim Login aus `CF-Connecting-IP` (Cloudflare setzt sie am Rand); ohne Cloudflare davor
  (lokal) wäre sie fälschbar — für die Produktion also nur hinter Cloudflare betreiben.
* Antworten: unbekannter Token 404; abgelaufen, verbraucht oder ersetzt 410 mit allgemeiner Meldung.
* Die Seite ist nicht indexierbar und sendet keinen Referrer (der Token steht in der Adresse).
* Tests: `tests/api/test_staffing_timesheets.py` (Ablauf, ungültig/abgelaufen/Wiederverwendung, Token eines
  anderen Zettels, Hash-Speicherung, Ratenbegrenzung, Eingabeprüfung).

Der Link wird **nicht** automatisch per E-Mail versendet; der Disponent kopiert ihn und schickt ihn selbst.

## Abrechnung, Export, Übernahme

**Rechnung aus freigegebenen Stundenzetteln** (Tabellen `staffing_invoices`, `staffing_invoice_lines`,
Migration `nomicon_02`). Es wird das vorhandene Rechnungs- und Freigabemodell der Vermittlung (`Fee`)
genutzt, nicht neu erfunden: gleiche Betragsfelder (netto, Umsatzsteuer aus `default_vat_rate`, brutto),
derselbe Status `InvoiceStatus` (Entwurf → gestellt → fällig → bezahlt, stornierbar) mit denselben
erlaubten Übergängen (`services/invoices.py::ALLOWED_INVOICE_TRANSITIONS`) und dieselbe Freigabe-Inbox:

* Aus **vom Kunden freigegebenen** Stundenzetteln (ein Kunde je Rechnung, Satz am Einsatz gesetzt) entsteht
  ein **Entwurf**; je Zettel eine Zeile (Name, Zeitraum, Stunden × Satz, kaufmännisch auf Cent gerundet).
  Ein Zettel steht nur auf **einer** Rechnung (eindeutig); beim Storno wird er wieder abrechenbar.
* **„Rechnung stellen“ durch einen Nicht-Admin** erzeugt eine Freigabe-Anfrage (`kind=invoice_issue`,
  `entity_type=staffing_invoice`), die ein Admin unter *Freigaben* entscheidet. Admins stellen direkt.
  Nicht-Admins dürfen sonst nur einen Entwurf verwerfen; fällig/bezahlt/Storno gestellter Rechnungen ist
  Admin-Sache.
* **Beträge sind Margendaten:** Nicht-Admins sehen weder Satz noch Netto/Brutto (auch nicht in den
  Listen); sie können Entwürfe aus Zetteln ihres Bereichs erstellen und das Stellen beantragen, ohne die
  Beträge zu kennen. Rechnungen sehen Admins und wer sie angelegt hat (bzw. dessen Teamleiter).
* Der Verrechnungssatz wird weiterhin nur von Admins am Einsatz gesetzt; ohne Satz ist ein Zettel nicht
  abrechenbar (Hinweis in der Oberfläche).
* Es gibt keine Rechnungsnummer und kein PDF; das Stellen setzt Datum und Zahlungsziel. Die
  Buchhaltung/Rechnungsstellung selbst bleibt außerhalb.

**CSV für die Lohnabrechnung** (`GET /api/v1/staffing/export/hours.csv?period_start=…&period_end=…`, **nur
Admins**, da der Stundenlohn enthalten ist): vom Kunden **freigegebene** Stunden je Leiharbeitnehmer und Kunde
im Zeitraum (nach Arbeitstag gefiltert). Format: UTF-8 **mit BOM**, Trennzeichen `;`, Zeilenende CRLF,
Dezimalkomma, Datum `TT.MM.JJJJ`. Spalten: `Personalnummer` (Kandidatennummer), `Nachname`, `Vorname`, `Kunde`,
`Entgeltgruppe`, `Wochenstunden`, `Stundenlohn EUR`, `Eintritt`, `Austritt`, `Zeitraum von`, `Zeitraum bis`,
`Arbeitstage`, `Stunden`, `Pausen Minuten`. Texte, die mit `=`, `+`, `-`, `@` beginnen, bekommen ein
vorangestelltes `'`, damit Excel sie nicht als Formel auswertet (CSV-Injection). Das System berechnet keine
Löhne, Steuern oder Sozialabgaben.

**Übernahme durch den Kunden** (`POST /assignments/{id}/takeover`, Knopf am aktiven Einsatz): legt einen
Vermittlungsprozess (`CandidateSubmission`) für Kandidat und Kunde an — Honorar in Prozent (Standard: der
Honorarsatz des Kunden, sonst angegeben) und, mit Jahresgehalt, das erwartete Honorar — und beendet den Einsatz
zum Übernahmedatum. Der Prozess **beginnt im ersten Status** (Quali-Call); es werden keine Stufen
vorgetäuscht (sie zählen in KPIs). Gibt es schon einen aktiven Prozess für Kandidat und Kunde, scheitert die
Übernahme (409) und der Einsatz bleibt aktiv. Mindesthonorar und Rechtsfragen zur Vermittlungsprovision nach
Überlassung (AÜG § 9) sind **nicht** abgebildet.

## Betrieb und Umgebungsvariablen

Es gibt **keine neuen Umgebungsvariablen**. Zu tun (nur der Nutzer, nicht von Claude angelegt):

* **Scheduled Job** auf DigitalOcean: `python scripts/run_staffing_deadlines.py` einmal täglich, z. B.
  `30 5 * * *` UTC (vor dem Versand der Fälligkeits-Mails); gleiche Variablen wie `send_due_reminders.py`
  (`CC_CRM_DATABASE_URL` u. a.).
* Migration `nomicon_01_staffing.py` läuft beim Deploy mit (siehe `KOPIE.md` zu Alembic-Heads).
* Erlaubnis nach AÜG unter *Überlassung → Compliance* eintragen (Admin); ohne sie kann kein Einsatz aktiv werden.

## Dummy-Daten

`python scripts/seed_data.py seed --candidates 60 --staffing 8` (nur lokale Entwicklungs-Datenbank,
nie Produktion). Es entstehen Leiharbeitnehmer, Verträge, eine Beispiel-Erlaubnis und Einsätze für
mehrere Fälle (Frist rot/gelb/grün, Lücke unter 3 Monaten, geplanter und beendeter Einsatz, Person In Auswahl ohne
Einsatz), alle über die echten Services und Regeln. Seit 2026-10-17 zusätzlich: eine Person mit **Vorzeit**
(10 Monate bei einem Kunden), ein **überfälliger** aktiver Einsatz, ein Einsatz mit **bestätigter
Überschneidung**, ein Einsatz **kurz vor/nach Equal Pay** (offen und bestätigt) und ein aktiver Einsatz, dessen
**Vertrag den Zeitraum nicht mehr deckt**. Das Seed-Skript ist idempotent (`seed_staffing.py` erkennt seine
Demo-Fälle an den Kandidaten).

## Offene rechtliche und fachliche Fragen (an Nutzer / Fachanwalt)

1. **Zählweise:** Kalendermonate oder Einsatztage? (Umgesetzt: Einsatztage, Lücken zählen nicht mit.)
2. **Verleiherwechsel / Konzernverbund:** Einsatzzeiten desselben Kunden bei anderen Verleihern zählen
   über die manuell erfassten **Vorzeiten** mit (seit 2026-10-17); eine automatische Erkennung gibt es nicht.
   Ob auch Zeiten innerhalb eines Konzernverbunds zusammengerechnet werden müssen, ist offen.
3. **Abweichungen durch Tarifvertrag** (Höchstdauer, Equal Pay nach 15 Monaten mit Branchenzuschlag):
   derzeit nur über die einstellbaren Werte abbildbar, nicht je Kunde/Branche.
4. **Überschrittene Höchstdauer:** soll die Aktivierung oder Verlängerung blockiert werden?
5. **Equal Pay:** welche Lohnbestandteile? Das System rechnet nicht, es erinnert nur.
6. **DSGVO:** Löschfristen für Überlassungs- und Lohnunterlagen, Verhalten beim Löschen/Anonymisieren
   eines Leiharbeitnehmers. Stand: Ein Kandidat mit Überlassungsprofil lässt sich nicht löschen (409, Verknüpfung
   `RESTRICT`), wohl aber anonymisieren — dabei bleiben Notizen am Leiharbeitnehmer, Einsatz und Vertrag sowie
   Stundenzettel unverändert stehen (sie können Personenbezug haben). Ob und was dort geleert wird, ist offen.
7. **Arbeitserlaubnis (Ausländer):** das Datum wird gespeichert, aber noch nicht für die Aktivierung geprüft.

## Was für andere Branchen konfigurierbar werden müsste (Analyse, nicht umgesetzt)

Die Anwendung ist für Steuer-/Rechtskanzleien gebaut. Für eine andere Branche (z. B. Industrie, Logistik)
müssten folgende Stellen konfigurierbar werden — bisher fest im Code:

* **Taxonomien:** `Rolle` (10 Steuer-/Rechtsrollen), `Abschlussart`, `Rechtsgebiet`
  (`backend/src/cc_crm/models/enums.py`, Labels in `frontend/src/lib/utils.ts`), samt Kandidatenfeldern
  (`ausbildung_titel`, `abschluesse`, `rechtsgebiete`, `examensnoten`, Umfeldfelder) und dem
  Lebenslauf-Extraktions-Prompt (`services/cv_extraction.py`).
* **Begriffe:** „Kanzlei/Kanzleien“ (ca. 60 Frontend- und 120 Backend-Dateien), Kanzleityp/-größe,
  Kanzleigruppe, Honorar-Stufen (Vermittlungshonorar in Prozent des Zielgehalts).
* **Texte und Vorlagen:** Profil-Generator (`services/profile_generator.py`) und
  `backend/templates/anonymes_profil_master.docx` (Commandeur-Stil), E-Mail-Vorlagen, Sourcing
  (Steuerberater-/Berufsregister-Quellen, `services/steuerberater_verzeichnis.py`, `wpk_berufsregister.py`).
* **Fachlogik:** Garantiezeit (`services/warranty.py`), Closing-Score, KPI-Punkte je Pipeline-Stufe.
* **Überlassung selbst** ist branchenneutral; nur die Checkliste (sechs feste Punkte) und die Branche je
  Vertrag (Freitext) wären je Branche anzupassen.

## Ergänzungen vom 2026-10-14 (Details in `docs/ANSICHTEN.md`)

- **Disposition** (`GET /staffing/disposition`): Kennzahlen, Bench, Stundenzettel-Eingang; Einsatz-Board auf `/ueberlassung`.
- **Übernahme-Fee nach Einsatzdauer:** einstellbare Staffel (Platzhalter-Startwerte, Admin, Compliance-Seite);
  `GET/PUT /staffing/takeover-fee-tiers`, Vorschau `GET /staffing/assignments/{id}/takeover-preview`.
- **Als Einsatz anbieten** (`POST /staffing/offer-from-candidate`): Profil „In Auswahl“, optional geplanter Einsatz.
- Alle `/staffing/**`-Routen verlangen die Ansicht **Überlassung**; der Kandidatenstatus warnt (oder sperrt), wenn
  für einen bereits im Austausch befindlichen Kandidaten ein Einsatz angelegt wird.
