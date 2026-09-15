"""Microsoft Graph adapter (Auftrag "M365-Postfach-Integration").

Delegated-OAuth-Anbindung fuer info@commandeurconsulting.de (und potenziell
weitere M365-Postfaecher): `auth.py` deckt den Authorization-Code-Flow
(Autorisierungs-URL, Code-Tausch, Refresh) ab, `client.py` die eigentlichen
Graph-API-Aufrufe (Mail senden/abrufen, Kalender lesen/schreiben). Beide
Module sind reine HTTP-Wrapper (httpx) ohne DB-Zugriff - die Verknuepfung
mit MailAccount/CalendarEvent passiert in services/mail_oauth.py,
services/graph_token_service.py, services/mail_sync.py, services/
mail_send.py und services/calendar_graph_sync.py.
"""
