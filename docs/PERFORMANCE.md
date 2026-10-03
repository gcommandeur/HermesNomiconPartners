# Leistung: Ziele und letzte Messung

Erzeugt von `backend/scripts/perf_bench.py`. **Das ist eine Messung auf einem Rechner an einem Tag, kein Garantiewert.** Vorgaenge ohne Messung stehen als "nicht gemessen" da, damit ein fehlender Eintrag nicht wie ein erfuellter wirkt.

| Vorgang | Ziel (p95) | p50 | p95 | p99 | Messungen | Ergebnis |
|---|---|---|---|---|---|---|
| Kandidat oeffnen | < 100 ms | 13.1 ms | 16.6 ms | 18.8 ms | 100 | innerhalb |
| Kandidatenliste (50, gefiltert) | < 150 ms | 89.2 ms | 120.5 ms | 134.3 ms | 100 | innerhalb |
| Kandidatensuche (Freitext) | < 200 ms | 769.5 ms | 1346.3 ms | 1472.2 ms | 100 | **ueber dem Ziel** |
| Kandidat speichern | < 150 ms | 22.0 ms | 29.6 ms | 32.2 ms | 100 | innerhalb |
| Prozessliste (50) | < 150 ms | 20.6 ms | 28.9 ms | 34.5 ms | 100 | innerhalb |
| Cockpit | < 500 ms | 395.2 ms | 435.8 ms | 714.5 ms | 20 | innerhalb |

Datenbestand: 50,000 Kandidaten, 500 Kanzleien, 5,000 Prozesse. Datenbank: postgresql.
Gemessen am 2026-10-03 auf Linux x86_64, Python 3.13.14, in-process (ohne Netzwerk, ohne DigitalOcean-Latenz).
