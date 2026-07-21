"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Building2, KanbanSquare, LayoutDashboard, MoreHorizontal, Users } from "lucide-react";
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

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 flex border-t border-white/10 bg-[#071426] pb-[env(safe-area-inset-bottom)] lg:hidden"
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
              active ? "text-[#69A7EA]" : "text-[#5F6B7A]",
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
        <MoreHorizontal size={20} strokeWidth={1.7} />
        Mehr
      </button>
    </nav>
  );
}
