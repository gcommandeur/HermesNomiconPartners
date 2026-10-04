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

## Design Nomicon Partners (Stand: erste Fassung, nur lokal)

- Farben: Navy `#001C4A`, Off-White `#FAF9F6`, Linien `#5A6C8A` (auf Navy) und `#9AA3B5` (auf Off-White); Schrift Poppins (lokal in `frontend/public/brand/fonts`, lizenzfrei OFL).
- Alles Design steckt in `frontend/src/app/brand-theme.css` und `frontend/public/brand/`. Hermes bleibt dunkel; hier sind Inhalt/Karten Off-White, Seitenleiste, untere Handy-Leiste und Anmeldeseite Navy.
- Logos in `frontend/public/brand/nomicon-*.png` (freigestellt aus den Markenbildern: `mark`, `wordmark`, `lockup` je `light` fuer Navy-Grund und `dark` fuer hellen Grund). Browser-Symbole `frontend/src/app/icon.png`, `apple-icon.png`.
- Lokale Werte (nicht im Repo): `frontend/.env.local` mit `NEXT_PUBLIC_BRAND_*`, `backend/.env` mit `CC_CRM_COMPANY_NAME`.

## Lokal ansehen (nur mit Dummy-Daten)

1. Backend: `backend/.venv` anlegen und `pip install -e ".[dev]"`, `backend/.env` mit `CC_CRM_DATABASE_URL=sqlite:///<absoluter Pfad>/cc_crm_nomicon.db`, dann `alembic upgrade head`, `python scripts/seed_data.py seed --clients 14 --candidates 60`, `python scripts/create_test_user.py <mail> <passwort> "Name" --admin`.
2. Start: Backend `uvicorn cc_crm.main:app --app-dir src --port 8000`, Frontend `pnpm dev` (nie `pnpm build` gleichzeitig).
3. Die Anmeldung braucht einen Code per E-Mail (Resend). Lokal ohne Resend: `dev-login.local.py` (nur lokal, von Git ausgeschlossen) erzeugt fuer den Test-Nutzer eine Sitzung - `python dev-login.local.py`, dann `http://localhost:3999` im Browser oeffnen. NIE auf Produktion verwenden.
