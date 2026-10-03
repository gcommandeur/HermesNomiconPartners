"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { primaryNavigation, utilityNavigation } from "./navigation";
import {
  getRecentCandidatesSnapshot,
  removeRecentCandidate,
  subscribeRecentCandidates,
  type RecentCandidate,
} from "@/lib/recent-candidates";
import { useCurrentUser } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

type NavigationItem = (typeof primaryNavigation)[number];

export function Sidebar({ collapsed, mobileOpen, onToggle, onMobileClose }: {
  collapsed: boolean;
  mobileOpen: boolean;
  onToggle: () => void;
  onMobileClose: () => void;
}) {
  const pathname = usePathname();
  // Bewusst kein useSyncExternalStore: dessen getSnapshot muss ueber
  // *mehrere* aufeinanderfolgende Aufrufe referenziell stabil sein, was mit
  // einem simplen localStorage-Read schwer zuverlaessig hinzubekommen ist
  // und in der Praxis zu "getSnapshot should be cached"-Fehlern fuehrte, die
  // das Rendering der Seite abbrechen liessen. useState+useEffect mit
  // eigenem Event-Listener ist hier robuster (ein Render mehr beim Mount
  // ist unproblematisch, da der Verlauf ohnehin erst nach der Hydration
  // relevant wird).
  const [recentCandidates, setRecentCandidates] = useState<RecentCandidate[]>([]);
  useEffect(() => {
    setRecentCandidates(getRecentCandidatesSnapshot());
    return subscribeRecentCandidates(() => setRecentCandidates(getRecentCandidatesSnapshot()));
  }, []);

  // "Geschäftsführung" ist admin-only (gleiche Sichtbarkeitslogik wie der
  // Administration-Block in einstellungen/page.tsx) - vor dem Laden von
  // useCurrentUser() sicherheitshalber ausgeblendet statt kurz aufzublitzen.
  const { data: meData } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const isTeamLead = meData?.data.role === "team_lead";
  const visiblePrimaryNavigation = primaryNavigation.filter(
    (item) => !item.adminOnly || isAdmin || (item.teamLeadToo && isTeamLead),
  );

  const renderItem = (item: NavigationItem) => {
    const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
    const Icon = item.icon;

    return (
      <Link
        key={item.href}
        href={item.href}
        title={collapsed ? item.label : undefined}
        onClick={onMobileClose}
        className={cn(
          "flex h-10 items-center gap-3 rounded-md px-3 text-[13px] transition-all duration-200",
          active ? "border-l-2 border-[#D8DADF] bg-gradient-to-r from-[#153A66]/80 to-[#102A4C]/55 text-white shadow-[inset_0_1px_0_rgba(255,255,255,.04)]" : "text-[#A7ADB7] hover:bg-[#203A5A]/45 hover:text-white hover:translate-x-[1px]",
          collapsed && "justify-center px-0",
        )}
      >
        <Icon size={17} strokeWidth={1.7} />
        {!collapsed && <span>{item.label}</span>}
      </Link>
    );
  };

  return (
    <>
      {mobileOpen && <button aria-label="Navigation schließen" className="fixed inset-0 z-40 bg-black/30 lg:hidden" onClick={onMobileClose} />}
      <aside className={cn(
        "fixed inset-y-0 left-0 z-50 flex flex-col border-r border-white/10 bg-[#071426] text-white shadow-[12px_0_40px_rgba(0,0,0,.22)] transition-all duration-200",
        collapsed ? "w-[76px]" : "w-[248px]",
        mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
      )}>
        <div className="flex h-24 items-center border-b border-white/10 px-4">
          <Link href="/" className={cn("flex min-w-0 items-center", collapsed ? "mx-auto" : "gap-3")} onClick={onMobileClose}>
            {/* Commandeur-Consulting-Logo (Nutzer-Vorgabe "zurueck zu unserem
                Commandeur Consulting Logo"): das CC-Monogramm bleibt
                transparent (Nutzer-Feedback "CC-Logo soll transparent
                sein") - der Platin-Farbverlauf hat inzwischen genug
                Kontrast, um auch ohne weisse Flaeche direkt auf dem dunklen
                Sidebar-Hintergrund klar erkennbar zu sein. Eingeklappt
                bewusst NUR das CC (Nutzer-Vorgabe "beim kleiner machen nur
                das CC ohne die Schrift"), Wortmarke nur im ausgeklappten
                Zustand daneben - h-6 statt vorher h-9, sonst ragt der
                Schriftzug bei 1418:232 Bildseitenverhaeltnis ueber den
                verfuegbaren Platz neben dem Icon hinaus (Nutzer-Feedback
                "Schrift ... nicht ueber Grenze"). */}
            <Image src="/brand/commandeur-mark.png" alt="Commandeur Consulting" width={44} height={44} className="h-11 w-11 shrink-0 object-contain" priority />
            {!collapsed && (
              <Image
                src="/brand/commandeur-wordmark.png"
                alt="Commandeur Consulting"
                width={1418}
                height={232}
                className="h-6 w-auto max-w-full object-contain"
                priority
              />
            )}
          </Link>
          <button className="ml-auto shrink-0 text-white/60 hover:text-white lg:hidden" onClick={onMobileClose}><X size={18} /></button>
        </div>

        <nav className="scrollbar-subtle flex-1 space-y-1 overflow-y-auto px-3 py-5">
          {visiblePrimaryNavigation.map((item) => (
            <div key={item.href}>
              {renderItem(item)}
              {/* Zuletzt geoeffnete Kandidaten (Phase L.3, Bullhorn-Vorbild):
                  bleiben als eigene Eintraege unter "Kandidaten" erreichbar,
                  damit mehrere Profile parallel offen bleiben koennen. */}
              {item.href === "/kandidaten" && !collapsed && recentCandidates.length > 0 && (
                <div className="ml-[26px] mt-1 space-y-0.5 border-l border-white/10 pl-3">
                  {recentCandidates.map((recent) => {
                    const href = `/kandidaten/${recent.id}`;
                    const active = pathname === href;
                    return (
                      <div
                        key={recent.id}
                        className={cn(
                          "group flex h-8 items-center gap-1.5 rounded-md pr-1.5 text-[12px] transition-colors",
                          active ? "text-white" : "text-[#8a9095] hover:text-white",
                        )}
                      >
                        <Link
                          href={href}
                          onClick={onMobileClose}
                          className="min-w-0 flex-1 truncate px-2 py-1"
                          title={recent.label}
                        >
                          {recent.label}
                        </Link>
                        <button
                          type="button"
                          aria-label={`${recent.label} schließen`}
                          title="Aus Verlauf entfernen"
                          onClick={(event) => {
                            event.preventDefault();
                            removeRecentCandidate(recent.id);
                          }}
                          className="shrink-0 rounded p-1 text-[#5b6167] opacity-0 hover:text-white group-hover:opacity-100"
                        >
                          <X size={11} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </nav>

        <div className="space-y-2 border-t border-white/10 p-3">
          {utilityNavigation.map(renderItem)}
          <button
            onClick={onToggle}
            className="hidden h-9 w-full items-center justify-center rounded-md text-white/55 hover:bg-white/8 hover:text-white lg:flex"
            aria-label={collapsed ? "Sidebar ausklappen" : "Sidebar einklappen"}
          >
            {collapsed ? <ChevronRight size={17} /> : <><ChevronLeft size={17} /><span className="ml-2 text-xs">Einklappen</span></>}
          </button>
        </div>
      </aside>
    </>
  );
}
