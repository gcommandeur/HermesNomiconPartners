# Archiv abgeschlossener Einmal-Skripte

Dieser Ordner sammelt Skripte, die eine **konkrete, abgeschlossene
Einmal-Aktion** durchgeführt haben (ein Import, ein Backfill, eine
Korrektur eines bestimmten historischen Vorfalls, eine Migration eines
bestimmten Altbestands, ...) - im Unterschied zu den generischen,
wiederholt nutzbaren Tools direkt in `backend/scripts/` (z.B.
`seed_data.py`, `create_api_key.py`, `backup_to_s3.py`,
`run_graph_sync.py`).

**Nichts hier wird gelöscht.** Der Zweck ist ausschließlich, dass
`backend/scripts/` beim Suchen eines aktuell nutzbaren Tools nicht mehr
von Dutzenden erledigten Einmal-Läufen überdeckt wird - die Skripte
bleiben als Referenz/Nachvollziehbarkeit erhalten (welche Korrektur wann
warum wie gemacht wurde) und funktionieren technisch unverändert weiter,
falls ein Lauf doch noch einmal reproduziert werden müsste.

## Woran ein Skript hier hingehört

Ein Skript gehört ins Archiv, wenn **mindestens eines** zutrifft:

- Der Dateiname trägt ein Datum (z.B. `_20260713`, `_20260916`) - das
  Datum markiert einen konkreten, bereits erledigten Lauf.
- Der Docstring beschreibt explizit eine Einmal-Aktion ("Einmalige
  Bereinigung", "One-time data migration", "Rückwirkender Nachtrag",
  "Schritt N eines Auftrags", einen konkreten historischen Vorfall/Import
  mit fester Datenquelle).
- Es ist Teil eines Auftrags, der als abgeschlossen gilt, oder hängt
  (per Sibling-Import, z.B. `from kanzlei_import_data import ...`) direkt
  an einem solchen Skript - beide gehören dann zusammen ins Archiv, sonst
  bricht der Import.

Ein Skript bleibt in `backend/scripts/`, wenn es **generisch und
wiederholt nutzbar** ist - kein Bezug zu einem bestimmten Datum/Vorfall/
Datenexport, sondern eine wiederverwendbare Funktion (Seed/Reset,
API-Key anlegen, Testnutzer anlegen, Backup, Format-Konvertierung, ein
laufender Scheduled Job, generische Audits/Integritätschecks ohne
Bezug zu einer bestimmten historischen Bereinigung).

## Konvention für neue Einmal-Skripte

Beim Anlegen eines neuen Einmal-Skripts (Backfill, Import, Korrektur
eines konkreten Vorfalls, ...):

1. Datum im Dateinamen (`_JJJJMMTT`-Suffix), damit es sich beim
   nächsten Aufräumen sofort als Einmal-Aktion zu erkennen gibt.
2. Docstring nennt den Anlass (welcher Auftrag/Vorfall/Datenexport) und
   macht klar, ob es lesend (READ-ONLY) oder schreibend ist.
3. Sobald der Lauf gegen Produktion erfolgreich durchgeführt und
   bestätigt wurde, direkt per `git mv scripts/<name>.py
   scripts/archive/<name>.py` hierher verschieben statt es in
   `backend/scripts/` liegen zu lassen - erspart die nächste
   Aufräum-Runde.
