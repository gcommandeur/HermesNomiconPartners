# Provisionsmodell — Nomicon-Modul

Nur in der Nomicon-Kopie (nicht in Hermes), **nur für Admins**: Es sind Gehalts- und Margendaten einzelner
Mitarbeiter. Sichtbar in der Geschäftsführer-Ansicht (`/geschaeftsfuehrung`, Abschnitt „Provisionsmodell“; Teamleiter
sehen die Seite, aber diesen Abschnitt nicht). Alle Schnittstellen unter `/api/v1/commission/…` verlangen Admin (403).

> **Wichtig:** Die Excel „Nomicon_Provisionsmodell“ liegt der Entwicklung **nicht** vor. Startwerte stammen aus der
> Beschreibung des Auftrags; die Rechenregeln sind daraus **abgeleitete Annahmen** (unten) und müssen mit den
> Beispielzahlen der Excel abgeglichen werden. Die Tests rechnen von Hand nach den hier dokumentierten Annahmen — bei
> einer Abweichung zur Excel ist die Annahme zu klären, nicht der Test anzupassen.

## Einstellbare Werte (Startwerte aus der Excel)

Gespeichert als JSON in `app_settings` (Schlüssel `commission_config`), bearbeitbar unter *Modell einstellen*, geprüft
(`commission_model.validate_config`), Änderungen im Audit-Log.

**Allgemein:** Umsatz ohne Provision je Quartal 10.000 €, Arbeitgeber-Faktor 1,23, Zusatzkosten 500 € je Monat und
Kopf, Honorarsatz auf Zielgehalt 28 %, Mindesthonorar 12.000 €, Ziel-Marge 50 %. (Honorarsatz und Mindesthonorar sind
hinterlegt, gehen aber **nicht** in die Provisionsrechnung ein.)

| Rang | Fix €/Monat | Satz 1 | bis Quartalsumsatz | Satz 2 | bis (zugleich Beförderungshürde) | Satz 3 |
|---|---|---|---|---|---|---|
| Junior | 3.000 | 10 % | 15.000 | 12 % | 30.000 | 14 % |
| Consultant | 3.500 | 12 % | 20.000 | 14 % | 40.000 | 16 % |
| Specialist | 3.500 | 14 % | 25.000 | 16 % | 55.000 | 18 % |
| Senior | 3.500 | 16 % | 35.000 | 18 % | 80.000 | 20 % |
| Principal | 3.750 | 18 % | 50.000 | 20 % | 120.000 | 22 % |
| Director | 4.000 | 22 % | 75.000 | 25 % | 160.000 | 30 % (keine Beförderung) |

## Rechenregeln (Annahmen)

Reine Funktionen ohne Datenbank in `services/commission_model.py`, je Quartal und Mitarbeiter:

1. **Gestaffelte Provision** (marginal), Schwellen bezogen auf den **gesamten** Quartalsumsatz R; die ersten
   `Umsatz ohne Provision` (F = 10.000 €) bringen keine Provision:
   `Provision = Satz1·(min(R,S1)−F) + Satz2·(min(R,S2)−max(S1,F)) + Satz3·(R−max(S2,F))`, je Summand nicht negativ.
   Beispiel Junior bei R = 40.000 €: 5.000·10 % + 15.000·12 % + 10.000·14 % = 500 + 1.800 + 1.400 = **3.700 €**.
2. **Kosten** = (3·Fixgehalt + Provision)·Arbeitgeber-Faktor + 3·Zusatzkosten
   (Junior, R = 40.000: (9.000+3.700)·1,23 + 1.500 = 17.121 €).
3. **Marge** = Umsatz − Kosten (22.879 € = 57,20 %). **Ampel:** grün ab Ziel-Marge, gelb ab Break-even, rot darunter.
   **Break-even** = Umsatz, bei dem die Marge 0 ist (Junior: 12.930,44 €); **Ziel-Umsatz** = Umsatz für die Ziel-Marge
   (Junior: 31.217,20 €). Berechnet per Intervallhalbierung; die Konfigurationsprüfung stellt sicher, dass jeder
   zusätzliche Euro Umsatz mehr bringt, als er an Provision samt Arbeitgeberanteil kostet.
4. **Beförderungs-Kaskade:** Erreicht der Quartalsumsatz die Schwelle 2 des Rangs, steigt der Mitarbeiter auf; danach
   wird gegen die Schwelle 2 des nächsten Rangs geprüft usw. (Junior mit 45.000 € → Specialist). Director: keine
   Beförderung. Die Beförderung wird **angezeigt und per Knopf bestätigt** (Rang setzen), nie automatisch vollzogen.

## Umsatzbasis (OFFEN — vom Nutzer zu bestätigen)

Was als Umsatz eines Mitarbeiters zählt, ist einstellbar (`revenue_basis`). Startannahme: **bezahlte
Vermittlungshonorare plus Überlassungsrechnungen ab „gestellt“** (AÜ-Rechnungssumme).

* Vermittlung: `Fee.amount_net`; Mitarbeiter = Verantwortlicher des Prozesses (`owner_user_id`); Datum = Zahlungsdatum
  (`paid`) oder Rechnungsdatum (`issued`: gestellt, fällig oder bezahlt).
* Überlassung: Rechnungszeile (`StaffingInvoiceLine.amount_net`); Mitarbeiter = Disponent des Einsatzes (ersatzweise
  Ersteller der Rechnung); Datum = Rechnungs- bzw. Zahlungsdatum je Einstellung. Entwürfe und stornierte Rechnungen
  zählen nie.
* Schalter: Vermittlungshonorare „nur bezahlte / ab gestellt“, Überlassung „mitzählen / nicht“, Überlassungsrechnungen
  „ab gestellt / nur bezahlte“.

## Rangzuordnung

Tabelle `commission_user_ranks` (Migration `nomicon_03_commission.py`): je Mitarbeiter ein Rang. Zuweisen,
ändern oder entfernen im Bericht; jede Änderung steht im Audit-Log. Umsatz von Mitarbeitern **ohne Rang** wird nicht
berechnet, aber als Hinweis „Umsatz ohne Rang“ gezeigt.

## Nicht enthalten / offene Fragen

1. **Umsatzbasis** (siehe oben) und ob Ersteller oder Disponent bei Überlassungsrechnungen zählt.
2. **Provision auf Quartalsumsatz gesamt oder je Honorar?** Umgesetzt: gestaffelt auf den Gesamtumsatz des Quartals.
3. **Freigrenze:** gilt sie je Quartal und Mitarbeiter (umgesetzt) und zieht sie nur von Stufe 1 ab?
4. **Beförderung:** auf Basis **eines** Quartals (umgesetzt) oder mehrerer? Gilt sie ab dem Folgequartal?
5. **Arbeitgeber-Faktor auch auf die Provision?** (umgesetzt: ja)
6. Das Mindesthonorar (12.000 €) und der Honorarsatz (28 %) sind hinterlegt, aber ohne Wirkung.
7. Kein Lohnabrechnungsmodul: Das Modell **berechnet** Provision und Marge für die Steuerung; ausgezahlt wird extern.
