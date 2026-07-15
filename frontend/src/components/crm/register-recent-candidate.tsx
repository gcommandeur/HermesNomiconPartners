"use client";

import { useEffect } from "react";
import { addRecentCandidate } from "@/lib/recent-candidates";

/** Traegt den aktuell geoeffneten Kandidaten in den "zuletzt geoeffnet"-
 * Verlauf ein, den die Sidebar anzeigt (Phase L.3). Rendert nichts. */
export function RegisterRecentCandidate({ id, label }: { id: string; label: string }) {
  useEffect(() => {
    addRecentCandidate({ id, label });
  }, [id, label]);
  return null;
}
