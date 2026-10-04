# Diese Installation ist eine Kopie von Hermes (zweite Firma)

Der Code kommt aus dem Hermes-Repo `gcommandeur/hermescrm` (Remote `upstream`).
Hier entstehen **keine** neuen Funktionen und **keine** Datenbank-Migrationen -
beides passiert nur in Hermes und kommt per Merge hierher.

## Neue Funktionen uebernehmen

```bash
git fetch upstream
git merge upstream/main      # nur gepruefte Staende, nie upstream/entwicklung
```

Einmalig pro Klon: `git config merge.ours.driver true` (sonst greift der Schutz
unten nicht). Der Push nach `upstream` ist gesperrt (`DISABLED`).

## Was in dieser Kopie anders ist (die Firmenschicht, per .gitattributes geschuetzt)

- `frontend/src/app/brand-theme.css` - Farben und Seitenhintergrund
- `frontend/public/brand/*` - Logos
- `backend/templates/*` - Briefkopf des anonymen Profils

Ausserdem per Umgebungsvariable (nicht im Code): `NEXT_PUBLIC_BRAND_APP_NAME`,
`NEXT_PUBLIC_BRAND_COMPANY_NAME`, `NEXT_PUBLIC_BRAND_MARK_SRC`,
`NEXT_PUBLIC_BRAND_WORDMARK_SRC`, `CC_CRM_COMPANY_NAME`,
`CC_CRM_PROFILE_TEMPLATE_PATH`.

## Eigene Daten

Eigene Datenbank, eigene DigitalOcean-App, eigene Microsoft-Entra-App, eigene
Schluessel (`CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY` u. a.). Nie Zugangsdaten aus
Hermes uebernehmen. Entwicklungsdaten nur Dummy-Daten.

## Wenn ein Merge Konflikte meldet

Konflikte ausserhalb der Firmenschicht bedeuten, dass in dieser Kopie etwas
geaendert wurde, das nur in Hermes geaendert werden darf. Die Aenderung in
Hermes machen lassen und hier verwerfen.
