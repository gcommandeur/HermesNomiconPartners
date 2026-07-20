"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, LogOut, Menu, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { QuickActionMenu } from "@/components/crm/quick-action-menu";
import { useDebouncedValue } from "@/lib/use-debounced-value";
import { getCandidatesPage, getClientsPage, getContactsPage } from "@/lib/api/queries";
import type { Candidate, ClientCompany, Contact } from "@/lib/api/types";

const MIN_QUERY_LENGTH = 2;

interface GlobalSearchResults {
  candidates: Candidate[];
  clients: ClientCompany[];
  contacts: Contact[];
}

const emptyResults: GlobalSearchResults = { candidates: [], clients: [], contacts: [] };

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const requestIdRef = useRef(0);

  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<GlobalSearchResults>(emptyResults);
  const debouncedQuery = useDebouncedValue(query.trim(), 300);

  async function handleLogout() {
    await fetch("/api/logout", { method: "POST" });
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
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  function goTo(path: string) {
    setQuery("");
    setOpen(false);
    router.push(path);
  }

  const showDropdown = open && debouncedQuery.length >= MIN_QUERY_LENGTH;
  const hasResults =
    results.candidates.length > 0 || results.clients.length > 0 || results.contacts.length > 0;

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center border-b border-white/10 bg-[#0D1B2E]/90 px-5 shadow-[0_10px_35px_rgba(0,0,0,.15)] backdrop-blur-xl lg:px-8">
      <button onClick={onMenu} className="mr-3 text-[#A7ADB7] lg:hidden" aria-label="Navigation öffnen"><Menu size={20} /></button>
      <div ref={containerRef} className="relative hidden w-full max-w-md sm:block">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#90969b]" size={16} />
        <input
          className="h-9 w-full rounded-md border border-white/10 bg-[#08111F]/70 pl-9 pr-3 text-sm text-white outline-none placeholder:text-[#747C89] focus:border-[#1F5FA8] focus:ring-2 focus:ring-[#1F5FA8]/20"
          placeholder="Kandidaten, Kanzleien oder Kontakte suchen"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            if (query.trim().length >= MIN_QUERY_LENGTH) setOpen(true);
          }}
        />
        {showDropdown && (
          <div className="absolute z-20 mt-1 max-h-96 w-full overflow-y-auto rounded-md border border-white/10 bg-[#0D1B2E] shadow-xl">
            {loading && <p className="px-3 py-2 text-sm text-[#747C89]">Sucht…</p>}
            {!loading && !hasResults && (
              <p className="px-3 py-2 text-sm text-[#747C89]">Keine Treffer</p>
            )}
            {!loading && results.candidates.length > 0 && (
              <div className="py-1">
                <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-[#747C89]">Kandidaten</p>
                {results.candidates.map((candidate) => (
                  <button
                    key={candidate.id}
                    type="button"
                    className="block w-full px-3 py-2 text-left text-sm text-[#F8FAFC] hover:bg-[#1F5FA8]/15"
                    onClick={() => goTo(`/kandidaten/${candidate.id}`)}
                  >
                    {candidate.first_name} {candidate.last_name}
                    {candidate.job_title && (
                      <span className="ml-2 text-xs text-[#747C89]">{candidate.job_title}</span>
                    )}
                  </button>
                ))}
              </div>
            )}
            {!loading && results.clients.length > 0 && (
              <div className="py-1">
                <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-[#747C89]">Kanzleien</p>
                {results.clients.map((client) => (
                  <button
                    key={client.id}
                    type="button"
                    className="block w-full px-3 py-2 text-left text-sm text-[#F8FAFC] hover:bg-[#1F5FA8]/15"
                    onClick={() => goTo(`/kanzleien/${client.id}`)}
                  >
                    {client.name}
                  </button>
                ))}
              </div>
            )}
            {!loading && results.contacts.length > 0 && (
              <div className="py-1">
                <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-[#747C89]">Kontakte</p>
                {results.contacts.map((contact) => (
                  <button
                    key={contact.id}
                    type="button"
                    className="block w-full px-3 py-2 text-left text-sm text-[#F8FAFC] hover:bg-[#1F5FA8]/15"
                    onClick={() => goTo(`/kanzleien/${contact.client_company_id}`)}
                  >
                    {contact.first_name} {contact.last_name}
                    {contact.client_company_name && (
                      <span className="ml-2 text-xs text-[#747C89]">{contact.client_company_name}</span>
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
        <Button variant="ghost" size="icon" aria-label="Benachrichtigungen"><Bell size={17} /></Button>
        <button className="ml-1 flex items-center gap-2 rounded-md p-1.5 hover:bg-white/6">
          <span className="grid size-8 place-items-center rounded-full bg-[#202327] text-[11px] font-semibold text-white">CC</span>
          <span className="hidden text-left md:block">
            <span className="block text-xs font-medium text-white">Commandeur</span>
            <span className="block text-[10px] text-[#858b91]">Consulting</span>
          </span>
        </button>
        <Button variant="ghost" size="icon" aria-label="Abmelden" onClick={handleLogout}><LogOut size={17} /></Button>
      </div>
    </header>
  );
}
