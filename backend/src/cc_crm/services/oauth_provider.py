"""Hermes als OAuth-Anbieter fuer Claude (Arbeitsplan 2, Q4).

Ablauf (nach der Claude-Connector-Doku, Stand 2026-10-04): Claude ruft /api/v1/mcp
ohne Token auf, bekommt 401 mit Verweis auf die Metadaten, registriert sich per
Dynamic Client Registration (oeffentlicher Client), leitet den Nutzer mit PKCE
(S256) zu /authorize; dort meldet sich der Nutzer mit seinem normalen Hermes-Login
an (Passwort+2FA oder Microsoft), bestaetigt die Verbindung auf der Zustimmungsseite
und Claude tauscht den Code gegen ein Token, das an GENAU diesen Hermes-Nutzer
gebunden ist (seine Rechte, sein Audit-Log, Entzug jederzeit).

Das Token gilt nur fuer /api/v1/mcp. Codes sind einmalig, Refresh-Tokens werden bei
jeder Nutzung erneuert (alte werden ungueltig). Es werden nur Hashes gespeichert."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cc_crm.core.config import get_settings
from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.core.security import generate_session_token, hash_token
from cc_crm.models.oauth import OAuthAuthorization, OAuthClient, OAuthToken
from cc_crm.models.user import User
from cc_crm.repositories.recruiting import AuditLogRepository

SCOPE = "mcp"
ACCESS_LIFETIME = timedelta(hours=1)
REFRESH_LIFETIME = timedelta(days=30)
REQUEST_LIFETIME = timedelta(minutes=10)
CODE_LIFETIME = timedelta(minutes=5)
MAX_CLIENTS = 500
MAX_REDIRECT_URIS = 5
MAX_CLIENT_NAME = 120
# Clients ohne jedes Token werden nach dieser Zeit beim naechsten Registrieren geloescht.
STALE_CLIENT_DAYS = 30
HOSTED_CALLBACKS = (
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
)
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1")


class OAuthError(Exception):
    """Fehler nach RFC 6749 (Token-Endpunkt) bzw. RFC 7591 (Registrierung)."""

    def __init__(self, error: str, description: str = "", status_code: int = 400) -> None:
        super().__init__(error)
        self.error = error
        self.description = description
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(UTC)


def public_base_url() -> str:
    """Oeffentliche Basis-URL des Backends (z.B. https://app.example/api/v1)."""
    settings = get_settings()
    origin = str(settings.cors_origins[0]).rstrip("/") if settings.cors_origins else ""
    return f"{origin}{settings.api_prefix}"


def frontend_origin() -> str:
    settings = get_settings()
    return str(settings.cors_origins[0]).rstrip("/") if settings.cors_origins else ""


def _loopback_key(uri: str) -> tuple[str, str, str] | None:
    parts = urlsplit(uri)
    if parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS:
        return (parts.scheme, parts.hostname, parts.path)
    return None


def redirect_uri_allowed(uri: str) -> bool:
    """Gehostete Claude-Apps: exakt die feste Callback-URL. Claude Code:
    Loopback (RFC 8252), der Port darf beliebig sein."""
    return uri in HOSTED_CALLBACKS or _loopback_key(uri) is not None


def redirect_matches(registered: list[Any], requested: str) -> bool:
    if requested in registered:
        return True
    wanted = _loopback_key(requested)
    return wanted is not None and any(_loopback_key(str(item)) == wanted for item in registered)


class OAuthProvider:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- Registrierung (RFC 7591) -----------------------------------------

    def register_client(self, metadata: dict[str, Any]) -> OAuthClient:
        uris = metadata.get("redirect_uris")
        if not isinstance(uris, list) or not uris or len(uris) > MAX_REDIRECT_URIS:
            raise OAuthError("invalid_redirect_uri", "redirect_uris fehlt oder ist ungueltig")
        for uri in uris:
            if not isinstance(uri, str) or not redirect_uri_allowed(uri):
                raise OAuthError("invalid_redirect_uri", "Diese Redirect-URI ist nicht erlaubt")
        raw_name = metadata.get("client_name")
        if raw_name is not None and not isinstance(raw_name, str):
            raise OAuthError("invalid_client_metadata", "client_name muss Text sein")
        name = (raw_name or "").strip() or "Claude"
        if len(name) > MAX_CLIENT_NAME or not name.isprintable():
            raise OAuthError(
                "invalid_client_metadata",
                f"client_name: hoechstens {MAX_CLIENT_NAME} druckbare Zeichen",
            )
        self._purge_unused_clients(older_than_days=STALE_CLIENT_DAYS)
        count = self.session.scalar(select(func.count()).select_from(OAuthClient)) or 0
        if count >= MAX_CLIENTS:
            # Aelteste Clients ohne Token verdraengen (jede neue Claude-Verbindung
            # registriert sich neu, siehe Doku).
            self._purge_unused_clients(oldest=count // 2)
            count = self.session.scalar(select(func.count()).select_from(OAuthClient)) or 0
            if count >= MAX_CLIENTS:
                # Harte Obergrenze: alle bestehenden Clients sind in Benutzung.
                raise OAuthError(
                    "temporarily_unavailable", "Zu viele registrierte Clients", status_code=503
                )
        client = OAuthClient(
            client_id=f"hmc_{secrets.token_urlsafe(24)}", client_name=name, redirect_uris=uris
        )
        self.session.add(client)
        self.session.commit()
        return client

    def _purge_unused_clients(
        self, *, older_than_days: int | None = None, oldest: int | None = None
    ) -> None:
        """Loescht registrierte Clients, die nie ein Token bekommen haben: entweder die
        aelter als `older_than_days` Tage oder die `oldest` aeltesten. Zugehoerige
        offene Anmelde-Anfragen gehen mit. Clients mit Token bleiben immer."""
        used = set(self.session.scalars(select(OAuthToken.client_id)).all())
        query = select(OAuthClient.client_id).order_by(OAuthClient.created_at)
        if older_than_days is not None:
            query = query.where(OAuthClient.created_at < _now() - timedelta(days=older_than_days))
        if oldest is not None:
            query = query.limit(oldest)
        drop = [c for c in self.session.scalars(query).all() if c not in used]
        if drop:
            self.session.execute(
                delete(OAuthAuthorization).where(OAuthAuthorization.client_id.in_(drop))
            )
            self.session.execute(delete(OAuthClient).where(OAuthClient.client_id.in_(drop)))

    def _client(self, client_id: str) -> OAuthClient:
        client = self.session.scalar(select(OAuthClient).where(OAuthClient.client_id == client_id))
        if client is None:
            raise OAuthError("invalid_client", "Unbekannter Client", 401)
        return client

    # --- Anmelde-Anfrage und Zustimmung ------------------------------------

    def begin_authorization(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        code_challenge: str,
        code_challenge_method: str,
        state: str | None,
        scope: str | None,
    ) -> OAuthAuthorization:
        client = self._client(client_id)
        if not redirect_matches(list(client.redirect_uris), redirect_uri):
            raise OAuthError("invalid_request", "redirect_uri passt nicht zum Client")
        if code_challenge_method != "S256" or not (43 <= len(code_challenge) <= 128):
            raise OAuthError("invalid_request", "PKCE mit S256 ist Pflicht")
        self.session.execute(
            delete(OAuthAuthorization).where(
                OAuthAuthorization.expires_at < _now() - timedelta(days=1)
            )
        )
        request = OAuthAuthorization(
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            state=state,
            scope=SCOPE,
            expires_at=_now() + REQUEST_LIFETIME,
        )
        self.session.add(request)
        self.session.commit()
        return request

    def pending_request(self, request_id: uuid.UUID) -> OAuthAuthorization:
        request = self.session.get(OAuthAuthorization, request_id)
        if (
            request is None
            or request.user_id is not None
            or request.used_at is not None
            or _aware(request.expires_at) < _now()
        ):
            raise EntityNotFoundError("Die Anfrage ist abgelaufen - bitte in Claude neu verbinden.")
        return request

    def consent_info(self, request_id: uuid.UUID) -> dict[str, str]:
        request = self.pending_request(request_id)
        client = self._client(request.client_id)
        host = urlsplit(request.redirect_uri).hostname or ""
        return {"client_name": client.client_name, "redirect_host": host, "scope": request.scope}

    def decide(self, user: User, request_id: uuid.UUID, approve: bool) -> str:
        """Gibt die URL zurueck, zu der der Browser zurueckgeschickt wird."""
        request = self.pending_request(request_id)
        params: dict[str, str] = {}
        if request.state:
            params["state"] = request.state
        if not approve:
            params["error"] = "access_denied"
            self.session.delete(request)
            self.session.commit()
            return _with_query(request.redirect_uri, params)
        code = f"hmk_{generate_session_token()}"
        request.code_hash = hash_token(code)
        request.user_id = user.id
        request.expires_at = _now() + CODE_LIFETIME
        AuditLogRepository(self.session).create(
            {
                "entity_type": "oauth_connection",
                "entity_id": user.id,
                "action": "claude_connection_approved",
                "changed_by": user.email,
                "new_values": {"client_id": request.client_id},
            }
        )
        self.session.commit()
        params["code"] = code
        return _with_query(request.redirect_uri, params)

    # --- Token-Endpunkt -----------------------------------------------------

    def exchange_code(
        self, *, client_id: str, code: str, redirect_uri: str, code_verifier: str
    ) -> dict[str, Any]:
        self._client(client_id)
        request = self.session.scalar(
            select(OAuthAuthorization).where(OAuthAuthorization.code_hash == hash_token(code))
        )
        if request is None or request.client_id != client_id or request.user_id is None:
            raise OAuthError("invalid_grant", "Code ungueltig")
        if request.used_at is not None:
            # Wiederverwendung eines Codes: alle daraus entstandenen Tokens widerrufen.
            self._revoke_for_authorization(request.id)
            raise OAuthError("invalid_grant", "Code wurde bereits verwendet")
        if _aware(request.expires_at) < _now() or request.redirect_uri != redirect_uri:
            raise OAuthError("invalid_grant", "Code abgelaufen oder redirect_uri passt nicht")
        digest = hashlib.sha256(code_verifier.encode("ascii", "ignore")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        if not hmac.compare_digest(expected, request.code_challenge):
            raise OAuthError("invalid_grant", "PKCE-Pruefung fehlgeschlagen")
        user = self.session.get(User, request.user_id)
        if user is None or not user.is_active:
            raise OAuthError("invalid_grant", "Nutzer nicht aktiv")
        request.used_at = _now()
        token = OAuthToken(
            user_id=user.id,
            client_id=client_id,
            authorization_id=request.id,
            access_hash="",
            refresh_hash="",
            access_expires_at=_now(),
            refresh_expires_at=_now(),
        )
        self.session.add(token)
        response = self._issue(token)
        self.session.commit()
        return response

    def refresh(self, *, client_id: str, refresh_token: str) -> dict[str, Any]:
        self._client(client_id)
        token = self.session.scalar(
            select(OAuthToken).where(OAuthToken.refresh_hash == hash_token(refresh_token))
        )
        if (
            token is None
            or token.client_id != client_id
            or token.revoked_at is not None
            or _aware(token.refresh_expires_at) < _now()
        ):
            raise OAuthError("invalid_grant", "Refresh-Token ungueltig")
        user = self.session.get(User, token.user_id)
        if user is None or not user.is_active:
            raise OAuthError("invalid_grant", "Nutzer nicht aktiv")
        response = self._issue(token)  # rotiert beide Tokens, das alte Refresh-Token ist danach tot
        self.session.commit()
        return response

    def _issue(self, token: OAuthToken) -> dict[str, Any]:
        access = f"hmo_{generate_session_token()}"
        refresh = f"hmr_{generate_session_token()}"
        token.access_hash = hash_token(access)
        token.refresh_hash = hash_token(refresh)
        token.access_expires_at = _now() + ACCESS_LIFETIME
        token.refresh_expires_at = _now() + REFRESH_LIFETIME
        return {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": int(ACCESS_LIFETIME.total_seconds()),
            "refresh_token": refresh,
            "scope": SCOPE,
        }

    def _revoke_for_authorization(self, authorization_id: uuid.UUID) -> None:
        for token in self.session.scalars(
            select(OAuthToken).where(OAuthToken.authorization_id == authorization_id)
        ):
            token.revoked_at = _now()
        self.session.commit()

    # --- Nutzung am MCP-Endpunkt -------------------------------------------

    def user_for_access_token(self, raw: str) -> User | None:
        token = self.session.scalar(
            select(OAuthToken).where(OAuthToken.access_hash == hash_token(raw))
        )
        if (
            token is None
            or token.revoked_at is not None
            or _aware(token.access_expires_at) < _now()
        ):
            return None
        user = self.session.get(User, token.user_id)
        if user is None or not user.is_active:  # Entzug bei Deaktivierung
            return None
        token.last_used_at = _now()
        self.session.commit()
        return user

    # --- Verwaltung durch den Nutzer ---------------------------------------

    def connections(self, user: User) -> list[tuple[OAuthToken, str]]:
        rows = self.session.execute(
            select(OAuthToken, OAuthClient.client_name)
            .join(OAuthClient, OAuthClient.client_id == OAuthToken.client_id, isouter=True)
            .where(OAuthToken.user_id == user.id, OAuthToken.revoked_at.is_(None))
            .order_by(OAuthToken.created_at.desc())
        ).all()
        return [(token, name or "Claude") for token, name in rows]

    def revoke(self, user: User, token_id: uuid.UUID) -> None:
        token = self.session.get(OAuthToken, token_id)
        if token is None or token.user_id != user.id:
            raise EntityNotFoundError("Verbindung nicht gefunden")
        token.revoked_at = _now()
        AuditLogRepository(self.session).create(
            {
                "entity_type": "oauth_connection",
                "entity_id": user.id,
                "action": "claude_connection_revoked",
                "changed_by": user.email,
            }
        )
        self.session.commit()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _with_query(url: str, params: dict[str, str]) -> str:
    separator = "&" if urlsplit(url).query else "?"
    return f"{url}{separator}{urlencode(params)}" if params else url


def ensure_enabled() -> None:
    if not get_settings().ai_enabled:
        raise BusinessRuleError("Die Claude-Schnittstelle ist nicht eingeschaltet.")
