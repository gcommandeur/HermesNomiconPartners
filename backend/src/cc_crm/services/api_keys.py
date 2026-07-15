import re
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import AuthenticationError
from cc_crm.core.security import generate_session_token, hash_token
from cc_crm.models.api_key import ApiKey
from cc_crm.models.user import User


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "agent"


class ApiKeyService:
    """Provisions long-lived credentials for agents/integrations.

    Each API key is backed by a dedicated, password-less service User so
    audit logs, activities and ownership fields work exactly like they do
    for human users.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, name: str) -> tuple[ApiKey, str]:
        service_email = f"service+{_slugify(name)}-{secrets.token_hex(4)}@cc-crm.local"
        user = User(
            email=service_email,
            hashed_password=hash_token(secrets.token_urlsafe(32)),
            display_name=f"Service: {name}",
        )
        self.session.add(user)
        self.session.flush()

        raw_key = f"ccrm_{generate_session_token()}"
        api_key = ApiKey(name=name, key_hash=hash_token(raw_key), user_id=user.id)
        self.session.add(api_key)
        self.session.commit()
        return api_key, raw_key

    def revoke(self, api_key_id: uuid.UUID) -> None:
        api_key = self.session.get(ApiKey, api_key_id)
        if api_key is not None:
            api_key.revoked_at = datetime.now(UTC)
            self.session.commit()

    def user_for_key(self, raw_key: str) -> User:
        key_hash = hash_token(raw_key)
        api_key = self.session.scalar(select(ApiKey).where(ApiKey.key_hash == key_hash))
        if api_key is None or api_key.revoked_at is not None:
            raise AuthenticationError("API key is invalid or revoked")
        api_key.last_used_at = datetime.now(UTC)
        user = self.session.get(User, api_key.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("API key is invalid or revoked")
        self.session.commit()
        return user
