"use client";

// Verlauf der zuletzt geoeffneten Kandidaten fuer die Sidebar (Phase L.3,
// Bullhorn-Vorbild): mehrere Kandidaten sollen parallel erreichbar bleiben,
// ohne dass ein Profil das andere ersetzt. Persistiert in localStorage,
// damit ein Reload die "offenen Tabs" nicht verliert. Ein CustomEvent
// benachrichtigt alle Abonnenten (Sidebar) im selben Tab sofort - das
// native "storage"-Event feuert nur in *anderen* Tabs/Fenstern.
const STORAGE_KEY = "cc_crm_recent_candidates";
const MAX_RECENT = 8;
const EVENT_NAME = "cc-crm-recent-candidates-changed";

export interface RecentCandidate {
  id: string;
  label: string;
}

function read(): RecentCandidate[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed as RecentCandidate[];
  } catch {
    return [];
  }
}

function write(entries: RecentCandidate[]) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  window.dispatchEvent(new Event(EVENT_NAME));
}

export function addRecentCandidate(entry: RecentCandidate) {
  const current = read().filter((item) => item.id !== entry.id);
  write([entry, ...current].slice(0, MAX_RECENT));
}

export function removeRecentCandidate(id: string) {
  write(read().filter((item) => item.id !== id));
}

export function subscribeRecentCandidates(callback: () => void) {
  window.addEventListener(EVENT_NAME, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(EVENT_NAME, callback);
    window.removeEventListener("storage", callback);
  };
}

export function getRecentCandidatesSnapshot(): RecentCandidate[] {
  return read();
}
