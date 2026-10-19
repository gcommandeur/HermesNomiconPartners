# Provisionsmodell — Nomicon-Modul

Nur in der Nomicon-Kopie (nicht in Hermes). Stand: Karriereplan „Nomicon_Karriereplan.pptx“ (Oktober 2026), alle
Entscheidungen vom Nutzer bestätigt.

* **Admin-Bericht** (Gehalts- und Margendaten): Geschäftsführer-Ansicht (`/geschaeftsfuehrung`, Abschnitt
  „Provisionsmodell“), Schnittstellen `/api/v1/commission/…` nur für Admins und hinter der Ansicht „Gesamt“.
* **Meine Provision** (`/provision`, `/api/v1/my-commission`): für jeden Mitarbeiter, siehe unten. Enthält nie Marge
  oder Firmenkosten.

> Die Excel „Nomicon_Provisionsmodell“ liegt der Entwicklung nicht vor. Die Tests rechnen von Hand nach den hier
> dokumentierten Regeln; bei einer Abweichung zur Excel ist die Regel zu klären, nicht der Test anzupassen.

## Einstellbare Werte (Startwerte laut Karriereplan)

Gespeichert als JSON in `app_settings` (Schlüssel `commission_config`), bearbeitbar unter *Modell einstellen*, geprüft
(`commission_model.validate_config`), Änderungen im Audit-Log. Namen, Reihenfolge und Anzahl der Stufen, Fixgehalt,
Sätze, Schwellen und Boni sind änderbar; **Verweise laufen über den Schlüssel (`key`), nicht über den Namen**.

**Allgemein:** Umsatz ohne Provision je Quartal 10.000 €, Arbeitgeber-Faktor 1,23, Zusatzkosten 500 € je Monat und
Kopf, Ziel-Marge 50 %, **Vermittlungsbonus 300 €** (Vermittlung) und **300 €** (Überlassung), getrennt einstellbar.
(Honorarsatz 28 % und Mindesthonorar 12.000 € sind hinterlegt, gehen aber nicht in die Rechnung ein.)

| Stufe | Fix/Jahr | Satz 1 | bis | Satz 2 | bis (= Beförderungshürde) | Satz 3 |
|---|---|---|---|---|---|---|
| Consultant | 40.000 € | 10 % | 25.000 | 12 % | 48.000 | 14 % |
| Specialist Consultant | 42.000 € | 15 % | 30.000 | 17,5 % | 60.000 | 20 % |
| Senior Consultant | 44.000 € | 20 % | 35.000 | 22,5 % | 96.000 | 25 % |
| Manager | 50.000 € | 25 % | 45.000 | 27,5 % | 120.000 | 30 % |
| Principal | 54.000 € | 30 % | 60.000 | 32,5 % | 144.000 | 35 % |
| Director | 60.000 € | 35 % | 85.000 | 37,5 % | 168.000 | 40 % (keine Beförderung) |

Junior entfällt. Das Fixgehalt steht **je Jahr**, der Quartalswert ist ein Viertel. Eine ältere gespeicherte
Konfiguration (Fix je Monat, Junior) gilt nicht mehr und wird durch diese Startwerte ersetzt; die Migration
`nomicon06deals` setzt Zuordnungen auf `junior` auf `consultant`.

## Rechenregeln

Reine Funktionen in `services/commission_model.py`, je Quartal und Mitarbeiter:

1. **Gestaffelte Provision** auf den Quartalsumsatz R, jeder Satz nur für seinen Bereich; die ersten 10.000 € sind frei:
   `Satz1·(min(R,S1)−F) + Satz2·(min(R,S2)−max(S1,F)) + Satz3·(R−max(S2,F))`, je Summand nicht negativ.
   Beispiel Consultant, R = 40.000 €: 15.000·10 % + 15.000·12 % = 1.500 + 1.800 = **3.300 €**.
2. **Bonus** = Vermittlungs-Deals·300 € + Überlassungs-Deals·300 €, einmalig je Deal, unabhängig von der Dealgröße. Er ist
   **nicht** Teil des provisionspflichtigen Umsatzes.
3. **Brutto im Quartal = Fixgehalt im Quartal + Provision + Bonus.**
4. **Kosten** = (Fix im Quartal + Provision + Bonus)·Arbeitgeber-Faktor + 3·Zusatzkosten. **Marge**, **Ampel**
   (grün ab Ziel-Marge, gelb ab Break-even, rot darunter), **Break-even** und **Ziel-Umsatz** nur für Admins; Break-even
   und Ziel-Umsatz rechnen ohne Bonus.
5. **Beförderung** (Kaskade): ab Quartalsumsatz ≥ Schwelle 2 des eigenen Rangs, danach gegen die nächste Schwelle usw.;
   Director nicht. Die Beförderung wird nur **angezeigt**, den Rang setzt ein Admin per Knopf.

Nachgerechnete Präsentationsbeispiele (Tests `test_commission_model.py`, **keine Abweichung**):

| | Umsatz | Deals | Provision | Bonus | Fix | Brutto |
|---|---|---|---|---|---|---|
| Consultant | 36.000 € | 3 | 2.820 € | 900 € | 10.000 € | 13.720 € |
| Manager | 96.000 € | 8 (5 + 3) | 22.775 € | 2.400 € | 12.500 € | 37.675 € |

Hinweis: Beim Director ergibt der Satz 40 % × Arbeitgeber-Faktor 1,23 = 49,2 % — die Ziel-Marge von 50 % ist damit nur bei
sehr hohem Umsatz erreichbar (Ziel-Umsatz rechnerisch ≈ 983.000 € je Quartal). Das ist eine Folge der Startwerte, kein
Fehler; Faktor, Ziel-Marge oder Sätze sind einstellbar.

## Deals und Bonus (`services/commission_deals.py`)

* **Vermittlung:** ein Prozess mit Platzierung (`Placement`) mit bezahlter Fee = ein Deal. Zeitpunkt: erstes Zahldatum
  einer Fee des Placements. Zuständig: Prozess-Owner.
* **Überlassung:** ein Einsatz = ein Deal, egal wie lange er läuft (6 Monate = **ein** Deal, kein Monatsbonus).
  Zeitpunkt: Zahldatum der ersten bezahlten Rechnung des Einsatzes. Zuständig: Disponent des Einsatzes (ersatzweise
  Ersteller der Rechnung).
* **Verlängerung = neuer Deal** (auch für dasselbe Paar Leiharbeitnehmer/Kunde), ebenso jeder neue Einsatz bei einem
  anderen Kunden. **Technische Erkennung:**
  * Rückt das geplante Ende eines Einsatzes nach hinten (`planned_end_date` neu > alt, beide gesetzt), schreibt die
    Einsatz-Änderung eine Zeile in `staffing_assignment_extensions` (`previous_end` = altes Ende, `new_end`,
    `extended_on`, Bearbeiter). Gleiches oder früheres Ende ist keine Verlängerung.
  * Eine Rechnungszeile gehört zum Abschnitt „Anzahl der Verlängerungen mit `previous_end` < Ende des abgerechneten
    Zeitraums“. Jeder Abschnitt mit mindestens einer bezahlten Rechnung ist **ein** Deal; sein Zeitpunkt ist das erste
    Zahldatum im Abschnitt.
  * Ein **Folgeeinsatz** (neuer `StaffingAssignment`, gleicher oder anderer Kunde) ist von selbst ein neuer Deal.
* **Zeitpunkt immer nach Zahldatum:** Der Bonus entsteht im Quartal der Zahlung. Entwürfe sowie gestellte und fällige
  Rechnungen geben weder Bonus noch Umsatz.
* **Annahme (offen, so umgesetzt):** Wird ein aktiver Einsatz später abgebrochen, bleibt der bereits entstandene Bonus;
  nicht bezahlte Rechnungen zählen nicht (Deals hängen nur an Zahlungen, nicht am Einsatzstatus).

## Umsatz

Einstellbar (`revenue_basis`), Startwert laut Karriereplan: **nur bezahlte** Vermittlungshonorare **und** nur bezahlte
Überlassungsrechnungen, jeweils im Quartal des Zahldatums.

* Vermittlung: `Fee.amount_net`, Mitarbeiter = Prozess-Owner.
* Überlassung: `StaffingInvoiceLine.amount_net` (je Monat und Leiharbeitnehmer, z. B. 4.000 €; 6 Monate = 24.000 €
  Umsatz, aber ein Deal), Mitarbeiter = Disponent. Ein Einsatz über zwei Quartale verteilt seinen Umsatz nach den
  Zahlungen auf beide; die gestaffelte Provision wird **je Quartal** berechnet.
* Schalter: Vermittlungshonorare „nur bezahlte / ab gestellt“, Überlassung „mitzählen / nicht“, Überlassungsrechnungen
  „nur bezahlte / ab gestellt“.
* Nicht bezahlte Rechnungen erscheinen in „Meine Provision“ nur als Hinweis **„erwartet“**, nie in der Provision.

## Meine Provision

`GET /api/v1/my-commission` (Parameter `user_id`, `year`, `quarter`) und `GET /api/v1/my-commission/people`, Seite
`/provision` und Karrierebalken auf der Startseite: links aktuelle Stufe, Mitte Balken mit Quartalsumsatz bis zur
Beförderungsschwelle (Betrag und Prozent), rechts nächste Stufe („Höchste Stufe“ beim obersten Rang). Darunter
Quartalsumsatz, Provision je Staffel mit lesbarer Rechnung („10.000 € frei …, 15.000 € zu 10 % …“), Bonus, Brutto und
für die Überlassung je Einsatz die bezahlten Monate und der Umsatz im Quartal.

**Rechte:** Mitarbeiter sehen nur sich selbst, Teamleiter sich und ihr Team (`manager_id`, live aus der DB), Admins
alle. Fremd **und** nicht vorhanden liefern dasselbe 404. Die Antwort beschreibt genau eine Person und enthält weder
Marge noch Arbeitgeberkosten (Tests: `tests/api/test_my_commission.py`). Die Route liegt bewusst nicht unter
`/commission`, damit sie nicht hinter der Ansicht „Gesamt“ gesperrt ist.

## Zeitstrahl und Monatswert (Meine Provision, seit 2026-10-19)

Abgerechnet wird weiter **je Quartal** (Rechenkern und Beförderungsregel unverändert). Die Seite `/provision` zeigt
zusätzlich, wie sich das Quartal Monat für Monat aufbaut: `GET /api/v1/my-commission/timeline` (Parameter `user_id`,
gleiche Rechte und gleiches 404 wie `/my-commission`, `services/commission_timeline.py`).

* **Monatswert:** die kumulierte Quartalsprovision bis Monatsende minus die kumulierte Provision bis Vormonatsende,
  jeweils nach denselben Staffeln. Die drei Monate ergeben also genau die Quartalsprovision. Fix und Bonus werden
  anteilig auf die Monate des Quartals verteilt (Bonus nach Zahldatum des Deals). Der **laufende Monat** ist
  „vorläufig, Abrechnung zum Quartalsende“.
* **Zeitstrahl:** die letzten 12 Monate mit Umsatz (nach Zahldatum) und Provision, Quartalsgrenzen markiert, der
  aktuelle Monat hervorgehoben; darunter eine Tabelle (Monat, Umsatz, Provision, Fix, Bonus, Summe).
* **Fortschritt zur nächsten Rolle:** Balken mit Abstand zur Beförderungsschwelle; auf der höchsten Stufe der Abstand
  zur nächsten Provisionsstufe. Drei Kacheln: „Dieser Monat“, „Dieses Quartal bisher“, „Bis zur nächsten Rolle“.
* **Annahme:** für alle Monate gilt die **aktuelle** Stufe der Person (kein Stufenverlauf gespeichert).
* **Demo-Daten:** `scripts/seed_commission_demo.py` (aus `seed_demo.py`): Demo-Vermittler als Senior Consultant bei etwa
  70 % der Manager-Schwelle, Demo-Admin mit Rang, neun Monate bezahlter Umsätze. Tests:
  `tests/services/test_commission_timeline.py`, `tests/api/test_my_commission_timeline.py`,
  `tests/test_seed_commission_demo.py`.

## Rangzuordnung

Tabelle `commission_user_ranks`: je Mitarbeiter ein Rang (`rank_key`). Umbenennen einer Stufe ändert keine Zuweisung;
wird eine Stufe entfernt, erscheint ihr Mitarbeiter im Bericht unter „ohne Rang“ und in „Meine Provision“ ohne Rang
(Admin weist neu zu). Jede Änderung steht im Audit-Log.

## Nicht enthalten / offene Fragen

1. Abgleich der Startwerte und Beispiele mit der Excel „Nomicon_Provisionsmodell“ (liegt nicht vor).
2. Beförderung auf Basis **eines** Quartals (umgesetzt) oder mehrerer? Gilt sie ab dem Folgequartal?
3. Verlängerung eines Einsatzes, dessen Ende zuvor leer war, wird nicht als Verlängerung erkannt (kein altes Ende).
4. Kein Lohnabrechnungsmodul: Das Modell **berechnet** Provision und Marge für die Steuerung; ausgezahlt wird extern.
