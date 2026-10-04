"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, LogOut, Menu, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { QuickActionMenu } from "@/components/crm/quick-action-menu";
import { useDebouncedValue } from "@/lib/use-debounced-value";
import { getCandidatesPage, getClientsPage, getContactsPage } from "@/lib/api/queries";
import { useCurrentUser } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { resetClientSession } from "@/lib/reset-client-session";
import type { Candidate, ClientCompany, Contact } from "@/lib/api/types";

const MIN_QUERY_LENGTH = 2;

interface GlobalSearchResults {
  candidates: Candidate[];
  clients: ClientCompany[];
  contacts: Contact[];
}

const emptyResults: GlobalSearchResults = { candidates: [], clients: [], contacts: [] };

function initialsOf(label: string): string {
  const words = label.split(/[\s@._-]+/).filter(Boolean);
  if (words.length === 0) return "?";
  return words
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join("");
}

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const requestIdRef = useRef(0);

  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const notificationsRef = useRef<HTMLDivElement>(null);
  const accountRef = useRef<HTMLDivElement>(null);
  const { data: currentUserData } = useCurrentUser();
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<GlobalSearchResults>(emptyResults);
  const debouncedQuery = useDebouncedValue(query.trim(), 300);

  const userLabel = currentUserData?.data.display_name || currentUserData?.data.email || "";
  const userInitials = initialsOf(userLabel);

  async function handleLogout() {
    await fetch("/api/logout", { method: "POST" });
    await resetClientSession();
    router.replace("/login");
    router.refresh();
  }

  // Globale Live-Suche ueber Kandidaten/Kanzleien/Kontakte (Prozesse/Vakanzen
  // bewusst ausgeschlossen - CandidateSubmission hat serverseitig keinen
  // Namens-Suchparameter). Request-ID verwirft veraltete Antworten, falls der
  // Suchtext sich aendert, waehrend ein aelterer Request noch laeuft.
  useEffect(() => {
    if (debouncedQuery.length < MIN_QUERY_LENGTH) {
      requestIdRef.current += 1;
      setResults(emptyResults);
      setLoading(false);
      return;
    }
    const requestId = ++requestIdRef.current;
    setLoading(true);
    Promise.all([
      getCandidatesPage({ search: debouncedQuery, limit: 5, offset: 0 }),
      getClientsPage({ search: debouncedQuery, limit: 5, offset: 0 }),
      getContactsPage({ search: debouncedQuery, limit: 5, offset: 0 }),
    ])
      .then(([candidates, clients, contacts]) => {
        if (requestIdRef.current !== requestId) return;
        setResults({
          candidates: candidates.data.items,
          clients: clients.data.items,
          contacts: contacts.data.items,
        });
      })
      .finally(() => {
        if (requestIdRef.current === requestId) setLoading(false);
      });
  }, [debouncedQuery]);

  useEffect(() => {
    if (query.trim().length >= MIN_QUERY_LENGTH) setOpen(true);
  }, [query]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
      if (notificationsRef.current && !notificationsRef.current.contains(event.target as Node)) {
        setNotificationsOpen(false);
      }
      if (accountRef.current && !accountRef.current.contains(event.target as Node)) {
        setAccountOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        setMobileSearchOpen(false);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Navigiert echt zur Detailseite (kein Quickview-Panel, siehe
  // candidates-table.tsx) - unmountet also /kandidaten komplett. Ist der
  // Nutzer GERADE auf der (evtl. gefilterten) Kandidatenliste, haengt ein
  // `back`-Parameter mit dem vollstaendigen Rueckweg (Pfad+Query) an, den
  // app/kandidaten/[id]/page.tsx als Ziel fuer "Zur Kandidatenliste" bevorzugt
  // - sonst ginge der Filter-/Suchzustand beim Zurueckkehren verloren (die
  // URL-Spiegelung in candidates-table.tsx greift ja erst NACH dem Mount).
  // Liest Pfad+Query bewusst per window.location statt usePathname()/
  // useSearchParams() aus - goTo() laeuft nur innerhalb eines Klick-Handlers,
  // eine Reaktivitaet auf Routenwechsel ist hier nicht noetig. Wichtiger
  // Grund: Topbar sitzt im globalen app-shell.tsx auf JEDER Seite -
  // useSearchParams() dort haette dort alle Seiten (auch /404) ohne eigene
  // Suspense-Grenze aus dem statischen Prerendering geworfen ("useSearchParams
  // should be wrapped in a suspense boundary").
  function goTo(path: string) {
    setQuery("");
    setOpen(false);
    if (window.location.pathname === "/kandidaten") {
      const currentQuery = window.location.search;
      const back = encodeURIComponent(`/kandidaten${currentQuery}`);
      const separator = path.includes("?") ? "&" : "?";
      router.push(`${path}${separator}back=${back}`);
      return;
    }
    router.push(path);
  }

  const showDropdown = open && debouncedQuery.length >= MIN_QUERY_LENGTH;
  const hasResults =
    results.candidates.length > 0 || results.clients.length > 0 || results.contacts.length > 0;

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center border-b border-white/10 bg-brand-surface/90 px-4 shadow-[0_10px_35px_rgba(0,0,0,.15)] backdrop-blur-xl sm:px-5 lg:px-8">
      {!mobileSearchOpen && (
        <button onClick={onMenu} className="mr-2 shrink-0 text-brand-silver lg:hidden" aria-label="Navigation öffnen"><Menu size={20} /></button>
      )}
      {/* Auf Mobile (<sm) ist die Suche standardmaessig ausgeblendet (kein
       * Platz neben Hamburger/Aktionen) - stattdessen oeffnet ein Icon-Button
       * sie als Vollbreite-Overlay ueber der restlichen Kopfzeile. */}
      <button
        onClick={() => setMobileSearchOpen(true)}
        className={cn("mr-2 shrink-0 text-brand-silver sm:hidden", mobileSearchOpen && "hidden")}
        aria-label="Suche öffnen"
      >
        <Search size={19} />
      </button>
      <div
        ref={containerRef}
        className={cn(
          "relative w-full max-w-md sm:block",
          mobileSearchOpen ? "absolute inset-x-0 top-0 z-40 flex h-16 items-center bg-brand-surface px-4 sm:static sm:z-auto sm:flex-none sm:bg-transparent sm:px-0" : "hidden sm:block",
        )}
      >
        {mobileSearchOpen && (
          <button
            onClick={() => { setMobileSearchOpen(false); setQuery(""); setOpen(false); }}
            className="mr-2 shrink-0 text-brand-silver sm:hidden"
            aria-label="Suche schließen"
          >
            <X size={19} />
          </button>
        )}
        <Search
          className={cn(
            "absolute top-1/2 -translate-y-1/2 text-[#90969b]",
            mobileSearchOpen ? "left-12 sm:left-3" : "left-3",
          )}
          size={16}
        />
        <input
          autoFocus={mobileSearchOpen}
          className={cn(
            "h-9 w-full rounded-md border border-white/10 bg-brand-bg/70 pr-3 text-sm text-white outline-none placeholder:text-brand-dim focus:border-brand-accent focus:ring-2 focus:ring-brand-accent/20",
            mobileSearchOpen ? "pl-12 sm:pl-9" : "pl-9",
          )}
          placeholder="Kandidaten, Kanzleien oder Kontakte suchen"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            if (query.trim().length >= MIN_QUERY_LENGTH) setOpen(true);
          }}
        />
        {showDropdown && (
          <div className="absolute z-20 mt-1 max-h-96 w-full overflow-y-auto rounded-md border border-white/10 bg-brand-surface shadow-xl">
            {loading && <p className="px-3 py-2 text-sm text-brand-dim">Sucht…</p>}
            {!loading && !hasResults && (
              <p className="px-3 py-2 text-sm text-brand-dim">Keine Treffer</p>
            )}
            {!loading && results.candidates.length > 0 && (
              <div className="py-1">
                <p className="px-3 py-1 text-[9.5px] font-semibold uppercase tracking-wider text-brand-dim">Kandidaten</p>
                {results.candidates.map((candidate) => (
                  <button
                    key={candidate.id}
                    type="button"
                    className="block w-full px-3 py-2 text-left text-sm text-brand-text hover:bg-brand-accent/15"
                    onClick={() => goTo(`/kandidaten/${candidate.id}`)}
                  >
                    {candidate.first_name} {candidate.last_name}
                    {candidate.job_title && (
                      <span className="ml-2 text-xs text-brand-dim">{candidate.job_title}</span>
                    )}
                  </button>
                ))}
              </div>
            )}
            {!loading && results.clients.length > 0 && (
              <div className="py-1">
                <p className="px-3 py-1 text-[9.5px] font-semibold uppercase tracking-wider text-brand-dim">Kanzleien</p>
                {results.clients.map((client) => (
                  <button
                    key={client.id}
                    type="button"
                    className="block w-full px-3 py-2 text-left text-sm text-brand-text hover:bg-brand-accent/15"
                    onClick={() => goTo(`/kanzleien/${client.id}`)}
                  >
                    {client.name}
                  </button>
                ))}
              </div>
            )}
            {!loading && results.contacts.length > 0 && (
              <div className="py-1">
                <p className="px-3 py-1 text-[9.5px] font-semibold uppercase tracking-wider text-brand-dim">Kontakte</p>
                {results.contacts.map((contact) => (
                  <button
                    key={contact.id}
                    type="button"
                    className="block w-full px-3 py-2 text-left text-sm text-brand-text hover:bg-brand-accent/15"
                    onClick={() => goTo(`/kanzleien/${contact.client_company_id}`)}
                  >
                    {contact.first_name} {contact.last_name}
                    {contact.client_company_name && (
                      <span className="ml-2 text-xs text-brand-dim">{contact.client_company_name}</span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      <div className="ml-auto flex items-center gap-2">
        <QuickActionMenu />
        <div ref={notificationsRef} className="relative">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Benachrichtigungen"
            onClick={() => setNotificationsOpen((current) => !current)}
          >
            <Bell size={17} />
          </Button>
          {notificationsOpen && (
            <div className="absolute right-0 z-20 mt-1 w-64 rounded-md border border-white/10 bg-brand-surface p-3 text-xs text-brand-muted shadow-xl">
              Keine neuen Benachrichtigungen.
            </div>
          )}
        </div>
        <div ref={accountRef} className="relative">
          <button
            className="ml-1 flex items-center gap-2 rounded-md p-1.5 hover:bg-white/6"
            onClick={() => setAccountOpen((current) => !current)}
          >
            <span className="grid size-8 place-items-center rounded-full bg-[#202327] text-[10.45px] font-semibold text-white">{userInitials}</span>
            <span className="hidden max-w-40 truncate text-left text-xs font-medium text-white md:block">
              {userLabel}
            </span>
          </button>
          {accountOpen && (
            <div className="absolute right-0 z-20 mt-1 w-56 rounded-md border border-white/10 bg-brand-surface p-1.5 text-xs shadow-xl">
              <div className="px-2.5 py-2 text-brand-soft">
                <p className="font-medium text-white">{currentUserData?.data.display_name ?? "Angemeldet"}</p>
                <p className="mt-0.5 text-[10.45px] text-brand-gray">{currentUserData?.data.email ?? ""}</p>
              </div>
              <button
                className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-brand-platinum hover:bg-white/8"
                onClick={() => { setAccountOpen(false); void handleLogout(); }}
              >
                <LogOut size={13} />Abmelden
              </button>
            </div>
          )}
        </div>
        <Button variant="ghost" size="icon" aria-label="Abmelden" onClick={handleLogout}><LogOut size={17} /></Button>
      </div>
    </header>
  );
}
