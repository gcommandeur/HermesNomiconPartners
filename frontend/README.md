# CC CRM Frontend

Premium-SaaS-Oberflaeche fuer das Recruiting-CRM von Commandeur Consulting.

## Voraussetzungen

- Node.js 20 oder neuer
- pnpm 10 oder neuer
- Optional: das FastAPI-Backend unter `../backend`

## Lokal starten

```powershell
cd frontend
Copy-Item .env.example .env.local
pnpm install
pnpm dev
```

Danach ist das Frontend unter `http://localhost:3000` erreichbar.

## API-Konfiguration

```env
NEXT_PUBLIC_CC_CRM_API_URL=http://127.0.0.1:8000/api/v1
```

Die URL wird ausschliesslich in `src/lib/api/client.ts` gelesen. Ist das Backend
nicht erreichbar, verwenden die ersten Screens kleine, nicht sensible Demo-Daten.

## Qualitaetschecks

```powershell
pnpm lint
pnpm typecheck
pnpm build
```

## Struktur

- `src/app`: Next.js App Router und Seiten
- `src/components/layout`: Sidebar, Topbar und App-Shell
- `src/components/ui`: lokale shadcn/ui-Bausteine
- `src/components/crm`: CRM-spezifische Tabellen, Karten und Statusanzeigen
- `src/lib/api`: API-Client, Typen und serverseitige Datenzugriffe
- `src/lib/demo-data.ts`: Entwicklungs-Fallbacks

## Aktuelle Arbeitsbereiche

- Operatives Cockpit mit Follow-ups, heißen Prozessen, KPIs und Quoten
- Kandidatenprofile mit Kurzprofil-Vorschlag und CV-Out-Historie
- Kanzleiprofile mit Konditionen, AGB-Status und erwarteten Fees
- CV-Out-Pipeline und Tabellenansicht
- Mandats-Matching-Vorbereitung mit 30-km-Radius
- Outlook-Vorlagen als kontrollierte Entwürfe
- Manuell pflegbare Sourcing-/LinkedIn-KPIs
