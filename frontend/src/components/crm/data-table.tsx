import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SortableHeader {
  label: string;
  key: string;
}

export type HeaderSpec = string | SortableHeader;

export function DataTable({
  headers,
  children,
  className,
  sortKey,
  sortDir,
  onSort,
}: {
  headers: HeaderSpec[];
  children: React.ReactNode;
  className?: string;
  sortKey?: string | null;
  sortDir?: "asc" | "desc";
  onSort?: (key: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-xl border bg-[linear-gradient(145deg,rgba(23,46,73,.96),rgba(13,27,46,.98))] shadow-[0_18px_50px_rgba(0,0,0,.16)]">
      <div className="scrollbar-subtle overflow-x-auto">
        <table className={cn("w-full min-w-[980px] border-collapse text-left text-sm", className)}>
          <thead>
            <tr className="border-b bg-brand-accent-soft/65">
              {headers.map((header) => {
                const isSortable = typeof header !== "string" && Boolean(onSort);
                const label = typeof header === "string" ? header : header.label;
                const key = typeof header === "string" ? null : header.key;
                const active = isSortable && sortKey === key;
                return (
                  <th
                    key={label}
                    onClick={isSortable && key ? () => onSort?.(key) : undefined}
                    className={cn(
                      "px-4 py-3 text-[10px] font-semibold uppercase tracking-[.1em] text-brand-soft",
                      isSortable && "cursor-pointer select-none hover:text-white",
                    )}
                  >
                    <span className="inline-flex items-center gap-1">
                      {label}
                      {isSortable && (
                        active ? (
                          sortDir === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} />
                        ) : (
                          <ArrowUpDown size={11} className="text-[#556072]" />
                        )
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="divide-y">{children}</tbody>
        </table>
      </div>
    </div>
  );
}
