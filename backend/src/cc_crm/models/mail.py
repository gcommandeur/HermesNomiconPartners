"""Angebundene E-Mail-Postfaecher (IMAP lesend, SMTP schreibend) und die
daraus eingelesenen Nachrichten.

Hintergrund: Hermes soll die zentrale Stelle fuer den gesamten Mailverkehr
werden - eingehende Mails aus den Postfaechern unter
@commandeurconsulting.de werden Kandidat:innen/Kanzlei-Kontakten zugeordnet
und als Activity abgelegt. Prioritaet hat info@, weil dort die
LinkedIn-InMail-Benachrichtigungen mit den Antworten der Kandidat:innen
auflaufen (siehe services/mail_classifier.py).

Passwoerter liegen ausschliesslich Fernet-verschluesselt in
MailAccount.encrypted_password und werden nie im Klartext geloggt oder ueber
die API zurueckgegeben (siehe services/mail_credentials.py).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from cc_crm.models.enums import (
    MailAccountOAuthStatus,
    MailAccountProvider,
    MailDirection,
    MailMatchStatus,
)


class MailAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mail_accounts"

    address: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    # Sprechendes Kuerzel fuer die Auswahl in der Oberflaeche, z.B.
    # "info-linkedin", "gege-persoenlich", "contact", "karriere", "lukas".
    label: Mapped[str] = mapped_column(String(80), nullable=False)

    # Wie dieses Konto angebunden ist (Auftrag "M365-Postfach-Integration") -
    # IMAP_SMTP (Default) nutzt die Felder direkt unten, MICROSOFT_GRAPH die
    # oauth_*-Felder weiter unten. Beide Gruppen sind deshalb nullable: eine
    # microsoft_graph-Zeile hat keine imap_host/smtp_host/username/
    # encrypted_password, eine imap_smtp-Zeile keine oauth_*-Felder.
    #
    # values_callable=... explizit gesetzt: SQLAlchemys Enum()-Typ speichert
    # OHNE values_callable per Default den Member-NAMEN ("IMAP_SMTP"), nicht
    # dessen .value ("imap_smtp") - Migration e5f6a7b8c9d0 hatte die
    # Bestandszeilen jedoch per server_default="imap_smtp" (klein, .value)
    # befuellt, was beim Zurueckladen mit
    # "'imap_smtp' is not among the defined enum values" scheiterte (Prod-
    # Vorfall nach Deploy von baabf41 - GET /mail-accounts lieferte 500,
    # sobald ein Postfach aus der Zeit vor dieser Migration existierte).
    # values_callable macht .value zur DB-Repraesentation, passend zum
    # bereits ausgelieferten Migrationswert - keine nachtraegliche
    # Daten-Migration der Bestandszeilen noetig.
    provider: Mapped[MailAccountProvider] = mapped_column(
        Enum(
            MailAccountProvider,
            native_enum=False,
            length=16,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=MailAccountProvider.IMAP_SMTP,
        nullable=False,
        index=True,
    )

    imap_host: Mapped[str | None] = mapped_column(String(255))
    imap_port: Mapped[int] = mapped_column(Integer, default=993, nullable=False)
    imap_use_ssl: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    smtp_host: Mapped[str | None] = mapped_column(String(255))
    smtp_port: Mapped[int] = mapped_column(Integer, default=587, nullable=False)
    smtp_use_ssl: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    username: Mapped[str | None] = mapped_column(String(320))
    # Fernet-Chiffrat, NIE Klartext. Entschluesselung nur unmittelbar vor dem
    # IMAP-/SMTP-Verbindungsaufbau (siehe services/mail_credentials.py).
    encrypted_password: Mapped[str | None] = mapped_column(Text)

    # --- Microsoft-Graph-OAuth (nur provider=microsoft_graph) -------------
    # Fernet-Chiffrat des Refresh-Tokens (dasselbe Verschluesselungsmodul wie
    # encrypted_password oben, siehe services/mail_credentials.py) - NIE der
    # Access-Token: der lebt nur ~60 Min. und wird bei jedem Sync-/Sende-Lauf
    # frisch aus dem Refresh-Token gezogen, nie persistiert (siehe
    # services/graph_token_service.py).
    encrypted_oauth_refresh_token: Mapped[str | None] = mapped_column(Text)
    # Gewaehrte Scopes als Diagnose-Info (z.B. bei einem spaeter reduzierten
    # Consent nachvollziehbar, welche Rechte tatsaechlich erteilt wurden).
    oauth_scopes: Mapped[str | None] = mapped_column(Text)
    # Gleicher values_callable-Grund wie bei provider oben - konsistente
    # .value-Speicherung fuer beide neuen Enum-Spalten dieser Integration.
    oauth_status: Mapped[MailAccountOAuthStatus | None] = mapped_column(
        Enum(
            MailAccountOAuthStatus,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        )
    )
    # Wer den OAuth-Login durchgefuehrt hat - bestimmt zugleich, wessen
    # CalendarEvent-Zeilen mit dem Kalender dieses Postfachs synchronisiert
    # werden (siehe services/calendar_graph_sync.py, Nutzer-Entscheidung:
    # Kalender-Sync ist pro Nutzer, kein gemeinsamer Firmenkalender).
    # use_alter=True: User.default_send_account_id verweist bereits auf
    # mail_accounts.id (Gegenrichtung) - ohne use_alter entsteht ein
    # Zwei-Tabellen-FK-Zyklus (mail_accounts<->users), den SQLite beim
    # Droppen der Tabellen (z.B. in Tests) nicht mehr sortieren kann.
    oauth_connected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
    )
    # Cursor fuer den inkrementellen Mail-Abruf per Microsoft-Graph-Delta-
    # Query - das providerspezifische Aequivalent zu last_seen_uid unten
    # (IMAP kennt keine Delta-Links, Graph keine UIDs).
    graph_delta_link: Mapped[str | None] = mapped_column(Text)
    # Eigener Cursor fuer den Kalender-Delta-Abruf (services/
    # calendar_graph_sync.py) - bewusst getrennt von graph_delta_link oben:
    # Mail- und Kalender-Sync fragen zwei unterschiedliche Graph-Endpoints
    # ab (/me/mailFolders/inbox/messages/delta vs. /me/calendar/events/
    # delta), ein gemeinsames Feld wuerde sich die beiden Cursor gegenseitig
    # ueberschreiben.
    graph_calendar_delta_link: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Standard-Absender fuer den CV-OUT-Versand an Kanzleien. Bewusst ein
    # umschaltbares DB-Flag statt einer fest verdrahteten Adresse, damit die
    # Versandadresse ohne Deploy aenderbar bleibt (Nutzer-Vorgabe). Der
    # persoenliche Override je Nutzer (User.default_send_account_id) hat
    # Vorrang, siehe dort.
    default_for_cv_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Rate-Limiting fuer den SMTP-Versand (services/mail_send.py) - je
    # Postfach konfigurierbar statt hart verdrahtet (Nutzer-Vorgabe), da
    # Versandgrenzen je Provider/Vertrag unterschiedlich sind. Konservative
    # Defaults: fuer United Domains (aktuell genutzter Hoster) liess sich
    # keine offizielle, dokumentierte Tagesgrenze ermitteln - ein oft
    # zitierter, nicht offiziell bestaetigter Anhaltspunkt liegt bei ca.
    # 250 Mails/Stunde; 8s Pause + 150/Tag bleibt bei einem vollen Achtstunden-
    # Lauf deutlich darunter, ohne die Werte hier als belastbar auszugeben -
    # in den Einstellungen ("E-Mails & Konten") pro Postfach anpassbar.
    send_throttle_seconds: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    daily_send_limit: Mapped[int] = mapped_column(Integer, default=150, nullable=False)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Hoechste bereits verarbeitete IMAP-UID. Bewusst zusaetzlich zu
    # last_synced_at: Serverzeiten weichen ab und Mails koennen nachtraeglich
    # zugestellt werden - ein reiner Zeitstempel-Filter uebersieht die dann.
    last_seen_uid: Mapped[str | None] = mapped_column(String(80))
    # Letzter Fehler beim Abruf (Diagnose in der Einstellungen-Oberflaeche).
    # Ein Fehler deaktiviert das Konto NICHT automatisch - sonst wuerde ein
    # einmaliger Netzwerkaussetzer das Postfach still abschalten.
    sync_error: Mapped[str | None] = mapped_column(Text)


class MailMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Eine eingelesene (oder selbst verschickte) Mail.

    Bewusst ein eigenes Modell statt einer Erweiterung von SourcingLead: bei
    einer LinkedIn-Mail kennen wir nur den Namen, waehrend SourcingLead auf
    Register-Daten (Arbeitgeber/Ort/PLZ/Quell-URL) ausgelegt ist und dessen
    approve_lead() daraus einen Kandidaten baut. Zusaetzlich liefert dieses
    Modell drei Dinge, die der Sync ohnehin braucht: Idempotenz (Dedup ueber
    message_id, ein zweiter Lauf darf keine Dubletten erzeugen), Erhalt der
    Rohdaten (Klassifikator-Fehler spaeter korrigierbar, ohne die Mail neu
    abzuholen) und die Erkennung selbst gesendeter Mails (direction).
    """

    __tablename__ = "mail_messages"

    mail_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # RFC-5322 Message-ID - Dedup-Schluessel ueber alle Laeufe hinweg.
    message_id: Mapped[str] = mapped_column(String(998), nullable=False, unique=True, index=True)
    # IMAP-UID des Kontos, fuer den inkrementellen Abruf (siehe
    # MailAccount.last_seen_uid). Nur innerhalb eines Kontos eindeutig.
    imap_uid: Mapped[str | None] = mapped_column(String(80))

    direction: Mapped[MailDirection] = mapped_column(
        Enum(MailDirection, native_enum=False, length=16),
        default=MailDirection.INBOUND,
        nullable=False,
        index=True,
    )

    from_name: Mapped[str | None] = mapped_column(String(320))
    from_address: Mapped[str | None] = mapped_column(String(320), index=True)
    subject: Mapped[str | None] = mapped_column(String(998))
    body_text: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    is_linkedin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    match_status: Mapped[MailMatchStatus] = mapped_column(
        Enum(MailMatchStatus, native_enum=False, length=24),
        default=MailMatchStatus.PENDING_REVIEW,
        nullable=False,
        index=True,
    )
    matched_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL"), index=True
    )
    matched_contact_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contact_persons.id", ondelete="SET NULL"), index=True
    )
    matched_client_company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("client_companies.id", ondelete="SET NULL"), index=True
    )
    # Rueckverweis auf die erzeugte Activity - verhindert doppelte Activities
    # bei einer erneuten Verarbeitung derselben Mail und macht im Review
    # sichtbar, was aus der Mail geworden ist.
    created_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL")
    )
    # Fehler beim Parsen genau dieser Mail. Eine kaputte Mail darf den
    # Sync-Lauf nicht abbrechen (gleiche Robustheit wie beim CSV-Import) -
    # sie wird mit Fehlertext abgelegt und uebersprungen.
    parse_error: Mapped[str | None] = mapped_column(Text)
