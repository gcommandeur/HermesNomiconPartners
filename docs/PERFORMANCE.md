# Leistung: Ziele und letzte Messung

Erzeugt von `backend/scripts/perf_bench.py`. **Das ist eine Messung auf einem Rechner an einem Tag, kein Garantiewert.** Vorgaenge ohne Messung stehen als "nicht gemessen" da, damit ein fehlender Eintrag nicht wie ein erfuellter wirkt.

| Vorgang | Ziel (p95) | p50 | p95 | p99 | Messungen | Ergebnis |
|---|---|---|---|---|---|---|
| Kandidat oeffnen | < 100 ms | 11.4 ms | 15.1 ms | 19.8 ms | 100 | innerhalb |
| Kandidatenliste (50, gefiltert) | < 150 ms | 89.2 ms | 117.4 ms | 122.5 ms | 100 | innerhalb |
| Kandidatensuche (Freitext) | < 200 ms | 17.8 ms | 24.2 ms | 25.5 ms | 100 | innerhalb |
| Kandidat speichern | < 150 ms | 22.2 ms | 29.8 ms | 34.8 ms | 100 | innerhalb |
| Prozessliste (50) | < 150 ms | 18.7 ms | 27.5 ms | 31.3 ms | 100 | innerhalb |
| Cockpit | < 500 ms | 58.7 ms | 80.3 ms | 416.3 ms | 20 | innerhalb |

Datenbestand: 50,000 Kandidaten, 500 Kanzleien, 5,000 Prozesse. Datenbank: postgresql.
Gemessen am 2026-10-03 auf Linux x86_64, Python 3.13.14, in-process (ohne Netzwerk, ohne DigitalOcean-Latenz).
