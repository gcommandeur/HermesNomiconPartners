import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Einfache Prev/Next-Steuerung für usePagination() - rein clientseitig
 * (keine Netzwerk-Requests), siehe lib/use-pagination.ts für den Hintergrund. */
export function PaginationControls({
  page,
  pageCount,
  onChange,
}: {
  page: number;
  pageCount: number;
  onChange: (page: number) => void;
}) {
  if (pageCount <= 1) return null;
  return (
    <div className="mt-3 flex items-center justify-end gap-2">
      <Button
        size="sm"
        variant="outline"
        disabled={page <= 0}
        onClick={() => onChange(page - 1)}
        aria-label="Vorherige Seite"
      >
        <ChevronLeft size={14} />
      </Button>
      <span className="text-xs text-[#8a9095]">
        Seite {page + 1} von {pageCount}
      </span>
      <Button
        size="sm"
        variant="outline"
        disabled={page >= pageCount - 1}
        onClick={() => onChange(page + 1)}
        aria-label="Nächste Seite"
      >
        <ChevronRight size={14} />
      </Button>
    </div>
  );
}
