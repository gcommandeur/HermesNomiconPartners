"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, X } from "lucide-react";
import {
  isNavigationItemActive,
  navigationGroups,
  utilityNavigation,
  visibleItems,
  type NavigationItem,
} from "./navigation";
import {
  getRecentCandidatesSnapshot,
  removeRecentCandidate,
  subscribeRecentCandidates,
  type RecentCandidate,
} from "@/lib/recent-candidates";
import { useAiProposalSummary, useCurrentUser, usePendingApprovalCount } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { brand } from "@/lib/brand";

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

  // Admin-only-Eintraege ("Geschäftsführung", Administration) sind vor dem Laden von
  // useCurrentUser() sicherheitshalber ausgeblendet statt kurz aufzublitzen.
  const { data: meData } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const isTeamLead = meData?.data.role === "team_lead";
  const pendingApprovals = usePendingApprovalCount(isAdmin);
  const ai = useAiProposalSummary();
  const visibleGroups = navigationGroups
    .filter((group) => !group.adminOnly || isAdmin)
    .map((group) => ({
      ...group,
      items: visibleItems(group.items, isAdmin, isTeamLead).filter(
        (item) => !item.requiresAi || ai.enabled,
      ),
    }))
    .filter((group) => group.items.length > 0);

  // Eingeklappte Gruppen, gemerkt pro Nutzer (localStorage). Erst nach dem Mount
  // gelesen (sonst Hydration-Abweichung), jede Storage-Nutzung in try/catch.
  const storageKey = `hermes-nav-closed-groups:${meData?.data.id ?? "anon"}`;
  const [closedGroups, setClosedGroups] = useState<string[]>([]);
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(storageKey);
      const parsed: unknown = raw ? JSON.parse(raw) : [];
      setClosedGroups(Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : []);
    } catch {
      setClosedGroups([]);
    }
  }, [storageKey]);
  const toggleGroup = (id: string) => {
    setClosedGroups((current) => {
      const next = current.includes(id) ? current.filter((entry) => entry !== id) : [...current, id];
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(next));
      } catch {
        // Storage nicht verfuegbar - Zustand gilt nur fuer diese Sitzung.
      }
      return next;
    });
  };

  const renderItem = (item: NavigationItem) => {
    const active = isNavigationItemActive(item, pathname);
    const Icon = item.icon;
    const badgeCount =
      item.badge === "approvals" ? pendingApprovals : item.badge === "aiProposals" ? ai.pending : 0;

    return (
      <Link
        key={item.href}
        href={item.href}
        title={collapsed ? item.label : undefined}
        onClick={onMobileClose}
        className={cn(
          "relative flex h-[38px] items-center gap-[11.4px] rounded-md px-[11.4px] text-[12.35px] transition-all duration-200",
          active ? "border-l-2 border-brand-platinum bg-gradient-to-r from-brand-accent-strong/80 to-brand-accent-soft/55 text-white shadow-[inset_0_1px_0_rgba(255,255,255,.04)]" : "text-brand-silver hover:bg-brand-hover/45 hover:text-white hover:translate-x-[1px]",
          collapsed && "justify-center px-0",
        )}
      >
        <Icon size={16} strokeWidth={1.7} />
        {!collapsed && <span className="flex-1">{item.label}</span>}
        {badgeCount > 0 && (
          collapsed ? (
            <span className="absolute right-2 top-2 size-2 rounded-full bg-brand-danger" aria-label={`${badgeCount} offen`} />
          ) : (
            <span className="min-w-5 rounded-full bg-brand-danger px-1.5 py-0.5 text-center text-[9.5px] font-semibold leading-none text-white">
              {badgeCount}
            </span>
          )
        )}
      </Link>
    );
  };

  return (
    <>
      {mobileOpen && <button aria-label="Navigation schließen" className="fixed inset-0 z-40 bg-black/30 lg:hidden" onClick={onMobileClose} />}
      <aside className={cn(
        "fixed inset-y-0 left-0 z-50 flex flex-col border-r border-white/10 bg-brand-sidebar text-white shadow-[12px_0_40px_rgba(0,0,0,.22)] transition-all duration-200",
        collapsed ? "w-[72px]" : "w-[236px]",
        mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
      )}>
        <div className="flex h-[91px] items-center border-b border-white/10 px-[15px]">
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
            <Image src={brand.markSrc} alt={brand.companyName} width={42} height={42} className="h-[42px] w-[42px] shrink-0 object-contain" priority />
            {!collapsed && (
              <Image
                src={brand.wordmarkSrc}
                alt={brand.companyName}
                width={1418}
                height={232}
                className="h-[23px] w-auto max-w-full object-contain"
                priority
              />
            )}
          </Link>
          <button className="ml-auto shrink-0 text-white/60 hover:text-white lg:hidden" onClick={onMobileClose}><X size={18} /></button>
        </div>

        <nav className="scrollbar-subtle flex-1 space-y-[3.8px] overflow-y-auto px-[11.4px] py-[19px]">
          {visibleGroups.map((group, groupIndex) => {
            const hasActiveItem = group.items.some((item) => isNavigationItemActive(item, pathname));
            // Die Gruppe der aktuellen Seite bleibt offen, auch wenn sie eingeklappt wurde.
            const open = !closedGroups.includes(group.id) || hasActiveItem;
            return (
              <div key={group.id} className={cn(groupIndex > 0 && (collapsed ? "mt-[11px] border-t border-white/10 pt-[11px]" : "mt-[15px]"))}>
                {!collapsed && (
                  <button
                    type="button"
                    onClick={() => toggleGroup(group.id)}
                    aria-expanded={open}
                    className="mb-[3.8px] flex h-[27px] w-full items-center justify-between px-[11.4px] text-[12.35px]! font-normal! text-brand-dim hover:text-brand-silver"
                  >
                    {group.label}
                    <ChevronDown size={11} className={cn("transition-transform", !open && "-rotate-90")} />
                  </button>
                )}
                {(collapsed || open) && (
                  <div className="space-y-[3.8px]">
                    {group.items.map((item) => (
                      <div key={item.href}>
                        {renderItem(item)}
                        {/* Zuletzt geoeffnete Kandidaten (Phase L.3, Bullhorn-Vorbild):
                            bleiben als eigene Eintraege unter "Kandidaten" erreichbar,
                            damit mehrere Profile parallel offen bleiben koennen. */}
                        {item.href === "/kandidaten" && !collapsed && recentCandidates.length > 0 && (
                          <div className="ml-[25px] mt-1 space-y-0.5 border-l border-white/10 pl-[11.4px]">
                            {recentCandidates.map((recent) => {
                              const href = `/kandidaten/${recent.id}`;
                              const active = pathname === href;
                              return (
                                <div
                                  key={recent.id}
                                  className={cn(
                                    "group flex h-[30px] items-center gap-1.5 rounded-md pr-1.5 text-[11.4px] transition-colors",
                                    active ? "text-white" : "text-brand-gray hover:text-white",
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
                                    className="shrink-0 rounded p-1 text-brand-gray-dark opacity-0 hover:text-white group-hover:opacity-100"
                                  >
                                    <X size={10} />
                                  </button>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
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
