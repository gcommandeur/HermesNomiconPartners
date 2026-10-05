"""Kennung, mit der sich Hermes bei externen Seiten (Verzeichnisse, Kanzlei-Websites)
meldet. Der Firmenname kommt aus der Konfiguration (CC_CRM_COMPANY_NAME), damit eine
Kopie fuer eine andere Firma nicht unter fremdem Namen auftritt."""

from cc_crm.core.config import get_settings


def sourcing_user_agent() -> str:
    return f"HermesCRM-Sourcing/1.0 ({get_settings().company_name}; Recruiting-Research)"
