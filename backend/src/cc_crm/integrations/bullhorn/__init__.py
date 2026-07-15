"""Bullhorn REST API adapter. See client.py and docs/BULLHORN_LINKEDIN_IMPORT.md."""

from cc_crm.integrations.bullhorn.client import BullhornAuthError, BullhornClient
from cc_crm.integrations.bullhorn.config import BullhornSettings

__all__ = ["BullhornAuthError", "BullhornClient", "BullhornSettings"]
