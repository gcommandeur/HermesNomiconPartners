import { cn } from "@/lib/utils";

/** Einheitliche Fehleranzeige für fehlgeschlagene API-Calls (Formular-Speichern,
 * Datei-Upload, etc.) - vorher als identisches Markup in 15 Komponenten
 * dupliziert, jetzt eine zentrale Stelle. Rendert nichts, wenn message leer/
 * null ist, damit Aufrufer weiterhin einfach `<ErrorBanner message={error} />`
 * ohne zusätzliches `{error && ...}` schreiben können. */
export function ErrorBanner({ message, className }: { message?: string | null; className?: string }) {
  if (!message) return null;
  return (
    <div
      className={cn(
        "rounded-lg border border-red-400/25 bg-red-950/30 p-3 text-xs text-red-200",
        className,
      )}
    >
      {message}
    </div>
  );
}
