# Plan: Outlook/Teams-Anbindung "einmal anmelden, alles verbunden"

Stand: 2026-10-03 (Cloud-Sitzung). **Status: umgesetzt am 2026-10-03 mit den empfohlenen Entscheidungen (Haken mit Vorschau, Teams-Link per Haken je Termin, `Mail.ReadWrite` unveraendert, weil der Posteingangs-Abgleich es nutzt). Offen fuer dich: Entra-ID-Einstellungen, siehe docs/DEPLOYMENT.md "Outlook & Teams".**

## Ziel
Wer sich mit seinem Microsoft-Konto anmeldet, hat danach ohne weiteren Schritt: Mail-Versand
aus dem eigenen Postfach, Kalenderabgleich, und bei Terminen mit Kandidaten eine echte
Outlook-Einladung mit Teams-Link an den Kandidaten.

## Was schon da ist (im Code geprueft)
- Mail senden ueber Graph (`integrations/microsoft_graph/client.py::send_mail`), Posteingangs-Abgleich (`fetch_inbox_delta`).
- Kalender zweiseitig (`services/calendar_graph_sync.py`, Zeitplan-Job): CRM-Termine nach Outlook, Outlook-Aenderungen zurueck.
- Zwei GETRENNTE Anmeldewege: "Mit Microsoft anmelden" (nur Identitaet, `LOGIN_SCOPES`, kein Token gespeichert) und "Postfach verbinden" (`GRAPH_SCOPES`: `offline_access User.Read Mail.Send Mail.ReadWrite Calendars.ReadWrite`, Refresh-Token am `MailAccount`).

## Was fehlt
1. **Ein Klick statt zwei:** Der Login holt noch keine Postfach-Rechte. Nutzer muss zusaetzlich "Postfach verbinden" ausfuehren.
2. **Kandidat bekommt nichts:** Das Event wird ohne Teilnehmer und ohne Teams-Link angelegt (`_event_payload` kennt weder `attendees` noch `isOnlineMeeting`).
3. **Sicherheitsluecke bei Schritt 2:** Der Event-Text ist heute `event.notes` = INTERNE Notizen. Sobald der Kandidat als Teilnehmer drin ist, saehe er sie. Es braucht einen getrennten, kandidatenfreundlichen Einladungstext.
4. Der Abgleich laeuft per Zeitplan - eine Einladung muss sofort beim Speichern rausgehen, nicht erst beim naechsten Lauf.
5. Verschieben/Absagen eines Termins muss die Einladung aktualisieren bzw. eine Absage senden; Zu-/Absage des Kandidaten soll im CRM sichtbar werden (`responseStatus` aus dem Delta).

## Umsetzung (Teilschritte)
- **O1 Ein-Klick-Anmeldung:** Login-Flow verlangt direkt `GRAPH_SCOPES`, legt/aktualisiert den `MailAccount` des Nutzers und speichert das Refresh-Token verschluesselt (bestehender Mechanismus). Bestehendes "Postfach verbinden" bleibt als Fallback/Reconnect. Kein Rechte-Zuwachs ueber das hinaus, was "Postfach verbinden" heute schon holt; zu pruefen, ob `Mail.ReadWrite` auf `Mail.Read` + `Mail.Send` verkleinert werden kann (weniger Rechte).
- **O2 Teams-Einladung:** `create_event/update_event` bekommen `attendees` und `isOnlineMeeting=true, onlineMeetingProvider=teamsForBusiness`. Dafuer ist KEIN zusaetzliches Graph-Recht noetig (`Calendars.ReadWrite` genuegt). Outlook verschickt die Einladung samt Teams-Link selbst, der Link wird im CRM am Termin/Interview gespeichert und in der Kandidatenmail nutzbar.
- **O3 Einladungstext:** eigenes Feld/Vorlage fuer den Kandidatentext; interne Notizen werden NIE an Outlook gesendet, wenn Teilnehmer gesetzt sind. Vorschau vor dem Senden.
- **O4 Sofort-Sync, Update, Absage, Antwortstatus** (siehe Punkte 4/5).
- **O5 Absicherung/Betrieb:** Banner "Verbindung abgelaufen - neu anmelden" bei Token-Fehler (`GraphAuthError`), Trennen-Knopf pro Nutzer, Audit-Eintrag je gesendeter Einladung, Hinweis im Datenschutztext.

## Sicherheit / Einstellungen
- Nur DELEGIERTE Rechte: jede:r Nutzer:in kommt nur an das EIGENE Postfach/den eigenen Kalender, nie an fremde.
- Refresh-Token nur verschluesselt in der DB, nie im Log/API. Beim Deaktivieren eines Nutzers Token loeschen.
- Entra-ID-Einstellungen (macht der Nutzer): Redirect-URI `https://hermescrm-v9sle.ondigitalocean.app/api/v1/auth/microsoft/callback`; Admin-Zustimmung fuer den Mandanten erteilen (sonst fragt jede Person einzeln bzw. wird blockiert); App auf "nur dieser Mandant" beschraenken, damit sich nur Kolleg:innen der Firma anmelden koennen.
- Einladungen gehen an externe Adressen: Standard = Haken "Einladung an Kandidat senden" mit Vorschau, nicht stillschweigend.

## Braucht deine Entscheidung
1. Einladung an Kandidaten: automatisch oder immer erst mit Haken/Vorschau? (Empfehlung: Haken, vorausgewaehlt.)
2. Darf `Mail.ReadWrite` bleiben oder verkleinern wir auf `Mail.Read`+`Mail.Send`? (Empfehlung: verkleinern, falls der Abgleich nichts verschiebt/loescht.)
3. Entra-ID: Mandant-only und Admin-Zustimmung - das kannst nur du bzw. euer Microsoft-Admin tun.
4. Teams-Link fuer jeden Interview-Termin automatisch oder nur auf Knopfdruck? (Empfehlung: Knopf/Haken je Termin, Standard an bei "Video".)
