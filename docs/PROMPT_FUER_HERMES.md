# Prompt fuer die Hermes-Sitzung (Nutzer kopiert ihn dorthin)

Hermes CRM und Nomicon Partners (`gcommandeur/HermesNomiconPartners`, Branch `entwicklung`) sind ab sofort
**zwei getrennte, gleichberechtigte Repos**. Nomicon ist keine Kopie und kein Nachzuegler mehr: kein Merge,
kein `upstream`, jede Seite hat ihre eigene Alembic-Kette, Migrationen duerfen in beiden Repos entstehen.
Damit nichts auseinanderlaeuft, wird **immer verglichen**.

**Deine Aufgaben in Hermes**
1. Zu Sitzungsbeginn und vor jedem Push: Nomicon lesend klonen oder aktualisieren
   (`git clone https://github.com/gcommandeur/HermesNomiconPartners` bzw. `git fetch`, Branch `entwicklung`)
   und im Nomicon-Klon `python scripts/vergleich.py --hermes <Pfad zu Hermes>` ausfuehren. Das zeigt, was
   seit dem letzten Pruefstand auf beiden Seiten passiert ist, welche Dateien beide Seiten angefasst haben
   und wie die Migrationsketten stehen. Das Register steht in `docs/VERGLEICH.md` (Nomicon).
2. Fehlerkorrekturen und Sicherheitsfixes aus Nomicon uebernimmst du (Patch/Cherry-Pick, nicht Merge).
   Features nur nach Absprache mit dem Nutzer. Uebernommene Migrationen bekommen in Hermes eine eigene neue
   Revision; danach muss `alembic heads` genau einen Kopf zeigen.
3. Schreibe nie in das Nomicon-Repo; Abweichungen und Uebernahmen traegt die Nomicon-Sitzung in
   `docs/VERGLEICH.md` ein. Halte in deinem Protokoll (`docs/PROTOKOLL.md`) fest, was du aus Nomicon
   uebernommen oder bewusst nicht uebernommen hast, mit Grund.
4. Trage diese Regel in das Hermes-`CLAUDE.md` und `docs/PROJEKT_STAND.md` ein.

**Was nur Nomicon hat (bewusst anders, nicht nach Hermes ziehen ohne Auftrag):** Nomicon-Design und
-Logo, Arbeitnehmerueberlassung (`staffing_*`, `/ueberlassung`, Stundenzettel mit Kundenfreigabe per Link),
Provisionsmodell (nur Admins), Profil-Briefkopf in Nomicon-Optik.

**Schon abgeglichen (Stand 2026-10-14):** Dein Kalender-Fix (Outlook-Termin ohne Betreff) und das entfernte
Wasserzeichen im DOCX-Export sind in Nomicon uebernommen. Moeglicher Kandidat fuer Hermes: neutrale
Firmenreste in der Oberflaeche (`document-panel.tsx` mit Brand-Firmenname, Platzhalter in
`einstellungen/postfaecher/page.tsx`); pruefe die Nomicon-Commits `7a4a4ac` und entscheide mit dem Nutzer.
