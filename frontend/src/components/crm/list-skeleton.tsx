/** Platzhalter-Balken fuer den EINMALIGEN initialen Ladezustand einer
 * serverseitig gesuchten/paginierten Liste (siehe use-server-search.ts).
 *
 * WICHTIG: nur bei `!hasLoadedOnce` rendern, NIEMALS bei SWRs eigenem
 * `isLoading` - das wird bei JEDEM Cache-Key-Wechsel kurz wahr (auch mit
 * `keepPreviousData`), also bei jeder debounce-verzoegerten Sucheingabe. Wer
 * hier stattdessen `isLoading` prueft, ersetzt FilterBar+Suchfeld bei jedem
 * Tastendruck durch dieses Skeleton und wieder zurueck - das erzeugt bei
 * jedem Tastendruck ein NEUES <input>-DOM-Element, das den Fokus verliert
 * (Nutzer muss nach jedem Buchstaben neu ins Feld klicken). Siehe
 * lib/api/use-server-search.ts fuer die volle Erklaerung und `hasLoadedOnce`/
 * `isValidating` als die richtigen Werte dafuer. */
export function ListSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="h-14 animate-pulse rounded-lg bg-brand-surface" />
      ))}
    </div>
  );
}
