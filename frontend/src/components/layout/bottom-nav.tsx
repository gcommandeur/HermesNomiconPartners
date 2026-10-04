"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Building2, KanbanSquare, LayoutDashboard, MoreHorizontal, Users } from "lucide-react";
import { useCurrentUser, usePendingApprovalCount } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

/** Mobile-only Bottom-Tab-Bar (analog zum bestehenden lg:hidden-Muster von
 * Sidebar/Topbar) - ersetzt auf schmalen Viewports das reine Hamburger-Menue
 * durch direkt erreichbare Haupt-Navigationspunkte. "Mehr" oeffnet dieselbe
 * Sidebar-Mobile-Overlay wie der Hamburger-Button in der Topbar (gleicher
 * onMenu-Handler aus app-shell.tsx), statt eine eigene Navigation aufzubauen. */
const items: { href: string; label: string; icon: typeof LayoutDashboard }[] = [
  { href: "/", label: "Übersicht", icon: LayoutDashboard },
  { href: "/prozesse", label: "Prozesse", icon: KanbanSquare },
  { href: "/kandidaten", label: "Kandidaten", icon: Users },
  { href: "/kanzleien", label: "Kanzleien", icon: Building2 },
];

export function BottomNav({ onMenu }: { onMenu: () => void }) {
  const pathname = usePathname();
  const { data: meData } = useCurrentUser();
  const pendingApprovals = usePendingApprovalCount(meData?.data.is_admin ?? false);

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 flex border-t border-white/10 bg-brand-sidebar pb-[env(safe-area-inset-bottom)] lg:hidden"
      aria-label="Hauptnavigation"
    >
      {items.map((item) => {
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex flex-1 flex-col items-center gap-1 py-2 text-[9px]",
              active ? "text-brand-accent-light" : "text-[#5F6B7A]",
            )}
          >
            <Icon size={20} strokeWidth={active ? 2 : 1.7} />
            {item.label}
          </Link>
        );
      })}
      <button
        type="button"
        onClick={onMenu}
        className="flex flex-1 flex-col items-center gap-1 py-2 text-[9px] text-[#5F6B7A]"
      >
        <span className="relative">
          <MoreHorizontal size={20} strokeWidth={1.7} />
          {pendingApprovals > 0 && (
            <span className="absolute -right-1 -top-0.5 size-2 rounded-full bg-brand-danger" aria-label={`${pendingApprovals} offene Freigaben`} />
          )}
        </span>
        {/* Eigenes span: globals.css setzt `font: inherit` auf Buttons ausserhalb der
            Tailwind-Layer, die Groesse am Button selbst wuerde ueberschrieben. */}
        <span className="text-[9px]">Mehr</span>
      </button>
    </nav>
  );
}
