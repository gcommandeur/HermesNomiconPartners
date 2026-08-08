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

MAX_ATTEMPTS = 3
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

    def record_failure(self, key: str) -> bool:
        """Zaehlt einen Fehlversuch und gibt True zurueck GENAU auf dem
        Versuch, der die Sperre neu ausloest (Uebergang von "noch erlaubt" zu
        "ab jetzt blockiert") - nicht bei jedem weiteren Versuch waehrend eine
        Sperre bereits aktiv ist. Damit kann der Aufrufer genau einmal pro
        Brute-Force-Ausbruch eine Sicherheitswarnung verschicken statt bei
        jedem einzelnen weiteren (ohnehin schon 429-blockierten) Versuch."""
        with self._lock:
            now = datetime.now(UTC)
            recent = self._prune(key, now)
            was_blocked = len(recent) >= self._max_attempts
            recent.append(now)
            self._failures[key] = recent
            return len(recent) >= self._max_attempts and not was_blocked

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

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @property
    def window(self) -> timedelta:
        return self._window


login_rate_limiter = LoginRateLimiter()


def client_ip(
    cf_connecting_ip: str | None, forwarded_for: str | None, direct_host: str | None
) -> str:
    """Ermittelt die Client-IP fuer das Rate-Limiting.

    Bevorzugt `CF-Connecting-IP`: die Produktivumgebung laeuft hinter
    Cloudflare (siehe docs/DEPLOYMENT.md) und Cloudflare setzt diesen Header
    selbst am Edge auf die tatsaechliche Verbindungs-IP - ein von aussen
    mitgeschickter Wert wird dabei von Cloudflare ueberschrieben, ist also
    nicht faelschbar.

    `X-Forwarded-For` dient nur noch als Fallback fuer Umgebungen ohne
    Cloudflare (lokale Entwicklung/Docker Compose). SICHERHEITSLUECKE, die
    genau deshalb behoben wurde: der erste Eintrag von X-Forwarded-For ist
    ein vom Client selbst frei waehlbarer Header-Wert - ein Angreifer konnte
    das Login-Rate-Limit dadurch mit einem beliebigen, bei jedem Request neu
    erfundenen X-Forwarded-For-Wert vollstaendig umgehen (live auf Produktion
    bestaetigt: unbegrenzte Passwort-Versuche trotz aktivem Limiter). Ohne
    CF-Connecting-IP (z.B. lokal) besteht dieses Risiko weiterhin, dort ist
    die Umgebung aber nicht oeffentlich exponiert."""
    if cf_connecting_ip:
        return cf_connecting_ip.strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return direct_host or "unknown"
