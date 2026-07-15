"""Minimal Bullhorn REST API adapter.

Implements Bullhorn's documented OAuth2 + REST login handshake:
1. GET  {auth_url}   with username/password -> redirect containing ?code=...
2. POST {token_url}  with the code          -> access_token
3. GET  {login_url}  with the access_token  -> BhRestToken + restUrl

Requires BULLHORN_CLIENT_ID, BULLHORN_CLIENT_SECRET, BULLHORN_USERNAME and
BULLHORN_PASSWORD to be set (see docs/BULLHORN_LINKEDIN_IMPORT.md). Nothing in
this module is exercised against a live Bullhorn tenant in this repository -
it is untested against production Bullhorn data and should be verified
against a sandbox before pulling real candidate/client data.
"""

from __future__ import annotations

from typing import Any

import httpx

from cc_crm.integrations.bullhorn.config import BullhornSettings

CANDIDATE_FIELDS = (
    "id,firstName,lastName,email,mobile,occupation,city,zip,dateAvailable,desiredSalary,customText1"
)
CLIENT_FIELDS = "id,name,email,phone,url,address,companyDescription"


class BullhornAuthError(RuntimeError):
    """Raised when authentication against Bullhorn fails or is not configured."""


class BullhornClient:
    def __init__(
        self,
        settings: BullhornSettings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or BullhornSettings()
        self._http = http_client or httpx.Client(timeout=30)
        self._rest_url: str | None = None
        self._rest_token: str | None = None

    def authenticate(self) -> None:
        if not self.settings.configured:
            raise BullhornAuthError(
                "Bullhorn ist nicht konfiguriert. Bitte BULLHORN_CLIENT_ID, "
                "BULLHORN_CLIENT_SECRET, BULLHORN_USERNAME und BULLHORN_PASSWORD setzen."
            )

        auth_response = self._http.get(
            self.settings.auth_url,
            params={
                "client_id": self.settings.client_id,
                "response_type": "code",
                "username": self.settings.username,
                "password": self.settings.password,
                "action": "Login",
            },
            follow_redirects=False,
        )
        code = self._extract_code(auth_response)

        token_response = self._http.post(
            self.settings.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
            },
        )
        token_response.raise_for_status()
        access_token = token_response.json()["access_token"]

        login_response = self._http.get(
            self.settings.login_url,
            params={"version": "*", "access_token": access_token},
        )
        login_response.raise_for_status()
        payload = login_response.json()
        self._rest_url = payload["restUrl"]
        self._rest_token = payload["BhRestToken"]

    @staticmethod
    def _extract_code(response: httpx.Response) -> str:
        location = response.headers.get("location", "")
        if "code=" not in location:
            raise BullhornAuthError(
                "Bullhorn OAuth-Code konnte nicht aus der Antwort gelesen werden. "
                "Pruefe Zugangsdaten und ob 2FA fuer den API-Benutzer deaktiviert ist."
            )
        return str(location).split("code=")[1].split("&")[0]

    def _ensure_session(self) -> None:
        if not self._rest_url or not self._rest_token:
            self.authenticate()

    def fetch_candidates(self, *, count: int = 200, start: int = 0) -> list[dict[str, Any]]:
        self._ensure_session()
        response = self._http.get(
            f"{self._rest_url}search/Candidate",
            params={
                "BhRestToken": self._rest_token,
                "query": "isDeleted:0",
                "fields": CANDIDATE_FIELDS,
                "count": count,
                "start": start,
            },
        )
        response.raise_for_status()
        return list(response.json().get("data", []))

    def fetch_client_corporations(
        self, *, count: int = 200, start: int = 0
    ) -> list[dict[str, Any]]:
        self._ensure_session()
        response = self._http.get(
            f"{self._rest_url}search/ClientCorporation",
            params={
                "BhRestToken": self._rest_token,
                "query": "isDeleted:0",
                "fields": CLIENT_FIELDS,
                "count": count,
                "start": start,
            },
        )
        response.raise_for_status()
        return list(response.json().get("data", []))

    @staticmethod
    def normalize_candidate(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "first_name": record.get("firstName"),
            "last_name": record.get("lastName"),
            "email": record.get("email") or None,
            "phone": record.get("mobile"),
            "job_title": record.get("occupation"),
            "city": record.get("city"),
            "postal_code": record.get("zip"),
            "salary_expectation": (
                str(record["desiredSalary"]) if record.get("desiredSalary") else None
            ),
        }

    @staticmethod
    def normalize_client(record: dict[str, Any]) -> dict[str, Any]:
        address = record.get("address") or {}
        return {
            "name": record.get("name"),
            "email": record.get("email") or None,
            "phone": record.get("phone"),
            "website": record.get("url"),
            "city": address.get("city"),
            "postal_code": address.get("zip"),
            "notes": record.get("companyDescription"),
        }
