# Leistung: Ziele und letzte Messung

Erzeugt von `backend/scripts/perf_bench.py`. **Das ist eine Messung auf einem Rechner an einem Tag, kein Garantiewert.** Vorgaenge ohne Messung stehen als "nicht gemessen" da, damit ein fehlender Eintrag nicht wie ein erfuellter wirkt.

| Vorgang | Ziel (p95) | p50 | p95 | p99 | Messungen | Ergebnis |
|---|---|---|---|---|---|---|
| Kandidat oeffnen | < 100 ms | 9.3 ms | 12.5 ms | 15.1 ms | 100 | innerhalb |
| Kandidatenliste (50, gefiltert) | < 150 ms | 53.5 ms | 99.3 ms | 114.7 ms | 100 | innerhalb |
| Kandidatensuche (Freitext) | < 200 ms | 13.9 ms | 19.8 ms | 31.1 ms | 100 | innerhalb |
| Kandidat speichern | < 150 ms | 19.4 ms | 24.7 ms | 60.1 ms | 100 | innerhalb |
| Prozessliste (50) | < 150 ms | 22.3 ms | 32.3 ms | 43.2 ms | 100 | innerhalb |
| Cockpit | < 500 ms | 92.1 ms | 115.7 ms | 174.8 ms | 20 | innerhalb |

Datenbestand: 200,000 Kandidaten, 2,000 Kanzleien, 20,000 Prozesse. Datenbank: postgresql.
Gemessen am 2026-10-04 auf Linux x86_64, Python 3.13.14, in-process (ohne Netzwerk, ohne DigitalOcean-Latenz).
