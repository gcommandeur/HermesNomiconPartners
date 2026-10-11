# Diese Installation ist eine Kopie von Hermes (zweite Firma)

Der Code kommt aus dem Hermes-Repo `gcommandeur/hermescrm` (Remote `upstream`).
Hier entstehen grundsaetzlich **keine** neuen Funktionen und **keine** Datenbank-Migrationen -
beides passiert nur in Hermes und kommt per Merge hierher. **Ausnahme (Nutzerauftrag
2026-10-11):** die Nomicon-eigenen Module (Arbeitnehmerueberlassung, Provisionsmodell), gebaut
in der merge-schonenden Bauweise unten.

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
3. Die Anmeldung braucht einen Code per E-Mail (Resend). Lokal ohne Resend: **`anmelden.local.cmd`** doppelklicken (ruft `dev-login.local.py` auf, beides nur lokal und von Git ausgeschlossen). Es meldet den Browser fuer den Test-Nutzer an, die Sitzung gilt ein Jahr, danach erscheint die Anmeldeseite lokal nicht mehr. Das Skript bricht ab, wenn die Datenbank nicht `cc_crm_nomicon.db` ist. Der Anmeldecode im Projekt bleibt unveraendert, damit die Kopie spaeter mit echten Daten sicher ist. NIE auf Produktion verwenden.


## Nomicon-eigener Code (Checkliste fuer Merge-Konflikte)

**Bauweise:** Nomicon-Code steht in NEUEN Dateien, die es in Hermes nicht gibt. Aenderungen an
gemeinsamen Dateien sind minimal und mit `NOMICON` markiert (`grep -rn NOMICON backend frontend`).
Tabellen tragen das Praefix `staffing_`, die Migration den Dateinamen-Praefix `nomicon_`.

**Neue Dateien (Backend):**
- `models/staffing.py`, `schemas/staffing.py`, `repositories/staffing.py`
- `services/staffing_audit.py`, `services/staffing_workers.py`, `services/staffing_assignments.py`,
  `services/staffing_licenses.py`, `services/staffing_deadlines.py` (Rechenkern),
  `services/staffing_settings.py`, `services/staffing_deadline_job.py`, `services/staffing_timesheets.py`, `services/staffing_invoices.py`, `services/staffing_takeover.py`
- `services/staffing_activation.py`, `services/staffing_overview.py`, `services/staffing_visibility.py`
- `api/staffing_dependencies.py` (Owner-Scope, `AssignmentAccess`/`TimesheetAccess`), `api/v1/staffing.py`,
  `api/v1/staffing_public.py` (Kundenfreigabe per Link, OHNE Login)
- `scripts/run_staffing_deadlines.py` (taeglicher Job), `scripts/seed_staffing.py` (Dummy-Daten)
- `docs/UEBERLASSUNG.md` (Datenmodell, Fristenregeln, Rechte, offene rechtliche Fragen),
  `docs/PROVISIONSMODELL.md`
- Provisionsmodell (nur Admins): `models/commission.py`, `schemas/commission.py`,
  `services/commission_model.py` (reine Rechenfunktionen), `commission_settings.py`, `commission_revenue.py`,
  `commission_report.py`, `api/v1/commission.py`, `tests/services/test_commission_model.py`,
  `tests/api/test_commission_api.py`; Frontend `components/crm/commission-report.tsx`,
  `lib/api/commission.ts`, `commission-hooks.ts`
- `alembic/versions/nomicon_01_staffing.py` (Revision `nomicon01staff`, haengt an `g3b5d7f9a1c2`) und
  `nomicon_02_staffing_invoices.py` (Revision `nomicon02invoices`, haengt an `nomicon01staff`) und
  `nomicon_03_commission.py` (Revision `nomicon03commission`, haengt an `nomicon02invoices`)
- `tests/services/test_staffing_services.py`, `test_staffing_deadlines.py`,
  `test_staffing_deadline_job.py`, `tests/api/test_staffing_api.py`,
  `tests/api/test_staffing_access_guard.py`, `tests/api/test_staffing_timesheets.py`, `tests/api/test_staffing_billing.py`,
  `tests/test_seed_staffing.py`

**Neue Dateien (Frontend):**
- `frontend/src/app/ueberlassung/**` (`layout.tsx`, `page.tsx`, `einsaetze/`, `leiharbeitnehmer/`, `compliance/`)
- `frontend/src/components/crm/staffing-*.tsx` (ui, overview-view, assignments-view, assignment-detail,
  assignment-create-modal, workers-view, compliance-view, candidate-panel)
- `frontend/src/lib/api/staffing.ts`, `staffing-hooks.ts`, `staffing-public.ts`, `frontend/src/lib/staffing-demo.ts`
- `frontend/src/app/stundenzettel/[token]/page.tsx` (Freigabeseite des Kunden, ohne Login),
  `frontend/src/app/api/stundenzettel/[...path]/route.ts` (schmale Weiterleitung, gibt die Client-IP weiter),
  `components/crm/staffing-timesheets-panel.tsx`, `staffing-timesheet-approval.tsx`,
  `staffing-billing-view.tsx`, `staffing-invoice-detail.tsx`; Seiten `app/ueberlassung/abrechnung/**`

**Markierte Aenderungen an gemeinsamen Dateien:**
- `backend/src/cc_crm/models/__init__.py` (Import und `__all__` der `Staffing*`-Modelle)
- `backend/src/cc_crm/services/approvals.py` (2 markierte Stellen: Freigabe `invoice_issue` fuer
  `entity_type="staffing_invoice"` und das Anzeigeetikett) - **bei Konflikten beide Zeilen behalten**
- `backend/scripts/seed_data.py` (Option `--staffing`, 3 markierte Stellen)
- `backend/src/cc_crm/api/v1/router.py` (Import und `include_router` fuer `staffing_router`,
  `staffing_public_router` und `commission_router`, 6 Zeilen)
- `frontend/src/app/geschaeftsfuehrung/page.tsx` (Import und eine Zeile `<CommissionReport />` fuer Admins)
- `frontend/src/middleware.ts` (Matcher: `api/stundenzettel` und `stundenzettel/` ohne Login erreichbar)
- `frontend/src/components/layout/conditional-shell.tsx` (keine Seitenleiste auf `/stundenzettel/...`)
- `frontend/src/components/layout/navigation.ts` (Icon-Import `HardHat` und die Gruppe `ueberlassung`)
- `frontend/src/app/kandidaten/[id]/page.tsx` (Import, Reiter `Überlassung` in `tabs`, ein `TabsContent`)
- `frontend/src/lib/api/openapi.json` und `schema.d.ts` sind ERZEUGT: nach jedem Merge aus Hermes neu
  erzeugen (`cd backend && python scripts/export_openapi.py && cd ../frontend && pnpm gen:api`),
  Konflikte dort nie von Hand loesen.

**Alembic-Heads:** Bekommt Hermes spaeter eine eigene Migration, entstehen nach dem Merge zwei
Heads (Hermes-Kopf und `nomicon01staff`). Dann eine Merge-Migration anlegen
(`alembic merge -m "merge hermes und nomicon" <head1> <head2>`) und `alembic heads` pruefen
(`tests/test_alembic_heads.py` erzwingt genau einen Head). Alternativ die Nomicon-Migration auf den
neuen Hermes-Kopf umhaengen (`down_revision`), solange sie noch nirgends ausgerollt ist.

