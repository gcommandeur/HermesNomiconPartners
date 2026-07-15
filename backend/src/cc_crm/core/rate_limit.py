"""Einfaches In-Memory-Rate-Limiting fuer den Login-Endpunkt (siehe
docs/DEPLOYMENT.md, dort bisher als offener Punkt vermerkt - aktuell gibt es
keinerlei Schutz gegen automatisiertes Passwort-Raten).

Bewusst kein Redis/externe Infrastruktur: die App laeuft als ein einzelner
uvicorn-Prozess fuer einen kleinen internen Nutzerkreis - ein simpler,
prozessinterner Zaehler reicht dafuer voellig aus und ist robuster (keine
zusaetzliche Abhaengigkeit, kein zusaetzlicher Netzwerk-Fehlerfall) als eine
externe Rate-Limiting-Bibliothek fuer diesen Massstab.

Zaehlt fehlgeschlagene Login-Versuche pro Client-IP in einem gleitenden
Zeitfenster; bei Ueberschreitung wird der naechste Versuch mit 429 abgelehnt,
BEVOR ueberhaupt ein Passwort-Vergleich stattfindet (verhindert nicht nur
Erfolg, sondern auch das Timing-Oracle wiederholter Passwort-Checks). Eine
erfolgreiche Anmeldung setzt den Zaehler fuer diese IP sofort zurueck.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from datetime import UTC, datetime, timedelta

MAX_ATTEMPTS = 5
WINDOW = timedelta(minutes=5)


class LoginRateLimiter:
    def __init__(self, max_attempts: int = MAX_ATTEMPTS, window: timedelta = WINDOW) -> None:
        self._max_attempts = max_attempts
        self._window = window
        self._failures: dict[str, list[datetime]] = defaultdict(list)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: datetime) -> list[datetime]:
        cutoff = now - self._window
        recent = [ts for ts in self._failures[key] if ts >= cutoff]
        self._failures[key] = recent
        return recent

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            recent = self._prune(key, datetime.now(UTC))
            return len(recent) >= self._max_attempts

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = datetime.now(UTC)
            self._prune(key, now)
            self._failures[key].append(now)

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def reset(self) -> None:
        """Nur fuer Tests - leert den gesamten In-Memory-Zustand, damit
        Tests sich nicht gegenseitig ueber den Prozess-weiten Singleton
        beeinflussen (dieselbe TestClient-Verbindung meldet immer dieselbe
        Client-IP)."""
        with self._lock:
            self._failures.clear()


login_rate_limiter = LoginRateLimiter()


def client_ip(forwarded_for: str | None, direct_host: str | None) -> str:
    """Bevorzugt X-Forwarded-For (erster Eintrag = urspruenglicher Client),
    da Railway/Vercel & Co. hinter einem Reverse Proxy laufen - ohne das
    wuerde jede Anfrage faelschlich als vom Proxy selbst kommend gezaehlt und
    das Rate-Limit griffe nie pro echtem Client."""
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return direct_host or "unknown"
