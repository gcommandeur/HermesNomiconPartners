"""DB-gestuetztes Rate-Limiting fuer Login/2FA-Verify (siehe
docs/DEPLOYMENT.md, dort bisher als offener Punkt vermerkt).

Kein Redis noetig: ein reiner Prozess-Zaehler (die fruehere Version dieser
Datei) haelt keinen Neustart/Deploy durch und wuerde bei mehreren
gleichzeitig laufenden App-Instanzen pro Instanz getrennt zaehlen, sich
also effektiv mit der Instanzzahl multiplizieren lassen - beides reale
Risiken auf DigitalOcean App Platform (Deploys/Skalierung). Die ohnehin
vorhandene Datenbank (siehe models/rate_limit_attempt.py) reicht fuer dieses
Zugriffsmuster (wenige Schreibzugriffe, kurze Zeitfenster) voellig aus,
ohne zusaetzliche Infrastruktur/Abhaengigkeit.

Zaehlt fehlgeschlagene Versuche pro Schluessel (IP/E-Mail/Account) als
Zeilen in `rate_limit_attempts` in einem gleitenden Zeitfenster; bei
Ueberschreitung wird der naechste Versuch mit 429 abgelehnt, BEVOR
ueberhaupt ein Passwort-/Code-Vergleich stattfindet (verhindert nicht nur
Erfolg, sondern auch das Timing-Oracle wiederholter Vergleiche). Eine
erfolgreiche Anmeldung/Verifizierung loescht die Zeilen fuer diesen
Schluessel sofort. Bei jedem Fehlversuch werden beilaeufig alle Zeilen
aelter als 1 Tag geloescht (kein separater Cron-Job noetig) - grosszuegig
laenger als jedes einzelne Zeitfenster, damit dieselbe Aufraeum-Regel fuer
alle vier Zaehler unten passt.

Gleiche oeffentliche Schnittstelle (is_blocked/record_failure/
record_success/reset) wie die fruehere In-Memory-Version, damit
api/v1/auth.py unveraendert bleibt - jede Methode oeffnet/schliesst ihre
eigene kurzlebige DB-Session (ueber das SessionLocal-Modulattribut, nicht
als direkt importierter Name, damit Tests es wie ueberall sonst im Projekt
per monkeypatch auf die isolierte Test-Engine umbiegen koennen, siehe
tests/conftest.py::client)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from cc_crm.infrastructure.database import session as db_session_module
from cc_crm.models.rate_limit_attempt import RateLimitAttempt

MAX_ATTEMPTS = 3
WINDOW = timedelta(minutes=5)

# Grosszuegig laenger als das laengste unten verwendete Zeitfenster (15 Min)
# - beim Aufraeumen wird bewusst nicht pro Scope unterschiedlich pariert,
# ein fester Wert reicht, weil Zeilen aelter als 1 Tag fuer JEDEN Zaehler
# hier garantiert irrelevant sind.
_CLEANUP_MAX_AGE = timedelta(days=1)


class LoginRateLimiter:
    def __init__(
        self, scope: str, max_attempts: int = MAX_ATTEMPTS, window: timedelta = WINDOW
    ) -> None:
        self._scope = scope
        self._max_attempts = max_attempts
        self._window = window

    def _count_recent(self, session, key: str, now: datetime) -> int:  # type: ignore[no-untyped-def]
        cutoff = now - self._window
        return int(
            session.scalar(
                select(func.count())
                .select_from(RateLimitAttempt)
                .where(
                    RateLimitAttempt.scope == self._scope,
                    RateLimitAttempt.key == key,
                    RateLimitAttempt.created_at >= cutoff,
                )
            )
            or 0
        )

    def is_blocked(self, key: str) -> bool:
        with db_session_module.SessionLocal() as session:
            return self._count_recent(session, key, datetime.now(UTC)) >= self._max_attempts

    def record_failure(self, key: str) -> bool:
        """Zaehlt einen Fehlversuch und gibt True zurueck GENAU auf dem
        Versuch, der die Sperre neu ausloest (Uebergang von "noch erlaubt" zu
        "ab jetzt blockiert") - nicht bei jedem weiteren Versuch waehrend eine
        Sperre bereits aktiv ist. Damit kann der Aufrufer genau einmal pro
        Brute-Force-Ausbruch eine Sicherheitswarnung verschicken statt bei
        jedem einzelnen weiteren (ohnehin schon 429-blockierten) Versuch."""
        now = datetime.now(UTC)
        with db_session_module.SessionLocal() as session:
            recent_count = self._count_recent(session, key, now)
            was_blocked = recent_count >= self._max_attempts
            session.add(RateLimitAttempt(scope=self._scope, key=key, created_at=now))
            # Beilaeufig beim Schreiben aufraeumen statt eines eigenen
            # Cron-Jobs - jede fehlgeschlagene Anmeldung/Verifizierung ist
            # ohnehin schon ein Schreibzugriff.
            session.execute(
                delete(RateLimitAttempt).where(
                    RateLimitAttempt.created_at < now - _CLEANUP_MAX_AGE
                )
            )
            session.commit()
            new_count = recent_count + 1
            return new_count >= self._max_attempts and not was_blocked

    def record_success(self, key: str) -> None:
        with db_session_module.SessionLocal() as session:
            session.execute(
                delete(RateLimitAttempt).where(
                    RateLimitAttempt.scope == self._scope, RateLimitAttempt.key == key
                )
            )
            session.commit()

    def reset(self) -> None:
        """Nur fuer Tests - leert den gesamten Zustand DIESES Scopes, damit
        Tests sich nicht gegenseitig ueber die (in Tests auf die isolierte
        Test-Engine umgebogene) Tabelle hinweg beeinflussen."""
        with db_session_module.SessionLocal() as session:
            session.execute(delete(RateLimitAttempt).where(RateLimitAttempt.scope == self._scope))
            session.commit()

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @property
    def window(self) -> timedelta:
        return self._window


login_rate_limiter = LoginRateLimiter("login_ip")

# Zweiter, unabhaengiger Zaehler PRO E-MAIL-ADRESSE (Login-Versuch), zusaetzlich
# zum bisherigen IP-basierten login_rate_limiter oben (Punkt 4 des Auftrags "5
# Hoch-Punkte umsetzen"). Der bisherige Zaehler schuetzt nicht gegen einen
# Angriff, der denselben Account ueber viele verschiedene IPs verteilt (z.B.
# ein Botnetz/Proxy-Pool) - ein solcher Angriff blieb bislang unter dem
# IP-Limit, weil jede einzelne IP fuer sich nie genug Fehlversuche sammelte.
# Eigene, groessere Grenzwerte (5 statt 3 Versuche, 15 statt 5 Minuten) als
# der IP-Zaehler: dieser Zaehler soll gezielten Account-Angriffen begegnen,
# nicht normale Nutzer schon nach dem dritten Tippfehler ueber ein breiteres
# Zeitfenster aussperren - beide Sperren greifen unabhaengig voneinander,
# je nachdem, welche zuerst ausloest (siehe api/v1/auth.py::login()).
EMAIL_MAX_ATTEMPTS = 5
EMAIL_WINDOW = timedelta(minutes=15)
email_login_rate_limiter = LoginRateLimiter(
    "login_email", max_attempts=EMAIL_MAX_ATTEMPTS, window=EMAIL_WINDOW
)


def email_rate_limit_key(email: str) -> str:
    """Normalisiert die E-Mail-Adresse als Zaehler-Schluessel - ohne dies
    wuerde "Foo@Bar.de" und "foo@bar.de" als zwei verschiedene Konten
    gezaehlt und die Sperre liesse sich durch Gross-/Kleinschreibung
    umgehen."""
    return email.strip().lower()


# Rate-Limiter fuer POST /auth/login/verify (Punkt 2 des Auftrags "3 Mittel-
# Punkte umsetzen"): der bestehende MAX_CODE_ATTEMPTS-Zaehler (siehe
# models/login_challenge.py) begrenzt Fehlversuche nur INNERHALB EINER
# Challenge (max. 5) - er greift nicht, wenn ein Angreifer, der bereits das
# richtige Passwort kennt, einfach viele neue Challenges erzeugt (jeder
# erfolgreiche /auth/login-Aufruf erstellt eine neue) und dann viele
# Verify-Versuche auf unterschiedliche challenge_ids verteilt. Jeder Versuch
# hasht den eingegebenen Code mit PBKDF2 (260k Iterationen, siehe
# core/security.py) - ohne ein zaehlerbasiertes Limit UEBER Challenges
# hinweg liesse sich der Server damit gezielt mit PBKDF2-Berechnungen
# belasten (CPU-DoS). Zwei unabhaengige Zaehler nach demselben Muster wie
# login_rate_limiter/email_login_rate_limiter oben: pro IP UND pro
# angefragtem Nutzer-Account (aus der Challenge aufgeloest, siehe
# AuthService.peek_challenge_user_id) - beide MUESSEN vor dem eigentlichen
# verify_challenge()-Aufruf (also vor dem PBKDF2-Hash) geprueft werden.
VERIFY_MAX_ATTEMPTS = 10
VERIFY_WINDOW = timedelta(minutes=5)
verify_ip_rate_limiter = LoginRateLimiter(
    "verify_ip", max_attempts=VERIFY_MAX_ATTEMPTS, window=VERIFY_WINDOW
)
verify_account_rate_limiter = LoginRateLimiter(
    "verify_account", max_attempts=VERIFY_MAX_ATTEMPTS, window=VERIFY_WINDOW
)


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
