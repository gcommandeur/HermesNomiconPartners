from pydantic_settings import BaseSettings, SettingsConfigDict


class BullhornSettings(BaseSettings):
    """Bullhorn REST API credentials, read from environment variables.

    None of these have real defaults on purpose - the adapter must not run
    against a live Bullhorn tenant unless the operator explicitly configures
    it. See docs/BULLHORN_LINKEDIN_IMPORT.md for setup instructions.
    """

    model_config = SettingsConfigDict(env_prefix="BULLHORN_", extra="ignore")

    client_id: str | None = None
    client_secret: str | None = None
    username: str | None = None
    password: str | None = None
    auth_url: str = "https://auth.bullhornstaffing.com/oauth/authorize"
    token_url: str = "https://auth.bullhornstaffing.com/oauth/token"
    login_url: str = "https://rest.bullhornstaffing.com/rest-services/login"

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.username and self.password)
