import type { DataResult } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_CC_CRM_API_URL?.replace(/\/$/, "");
const DEMO_MODE = process.env.NEXT_PUBLIC_CC_CRM_DEMO_MODE === "true";
export const apiBaseUrl = API_BASE_URL;
export const AUTH_COOKIE_NAME = "cc_crm_token";
// Muss mit SESSION_LIFETIME in backend/src/cc_crm/services/auth.py
// uebereinstimmen - der Cookie darf nicht laenger gueltig bleiben als das
// Backend-Token selbst, sonst haelt der Browser eine Session fuer aktiv, die
// serverseitig laengst abgelaufen ist.
export const AUTH_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24;

// Ohne ein explizites Timeout hängt ein server-seitiger fetch() (Server
// Components/Layout) bei einem falsch konfigurierten/unerreichbaren Backend
// (z.B. falscher Host, Backend down) am OS-TCP-Timeout (mehrere Minuten) statt
// mit einem klaren Fehler zu scheitern - jede Next.js-Seite blieb dadurch im
// Skeleton-Loading-Zustand haengen. 8s ist grosszuegig ueber der beobachteten
// echten Antwortzeit (<1s fuer alle Listen-Endpoints, siehe Phase-H-Bericht).
const API_TIMEOUT_MS = 8000;

function timeoutSignal(): AbortSignal {
  return AbortSignal.timeout(API_TIMEOUT_MS);
}

/** FastAPI error responses are JSON like {"detail": "..."}; showing that raw
 * in the UI ("{"detail":"..."}") looks broken. Extract just the message.
 *
 * Ein Gateway (z.B. DigitalOcean App Platform bei einem 504) antwortet bei
 * einem Fehler VOR unserem eigenen Backend nicht mit JSON, sondern mit einer
 * ganzen HTML-Fehlerseite - die landete zuvor 1:1 als Error-Message und wurde
 * roh im UI angezeigt (live beobachtet: kompletter HTML-Quelltext im
 * CV-Upload-Hinweis). Nicht-JSON-Antworten bekommen daher immer eine kurze,
 * generische Meldung statt des rohen Bodies. */
async function errorMessageFromResponse(response: Response): Promise<string> {
  const raw = await response.text();
  if (!raw) return `API antwortet mit ${response.status}`;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Kein JSON (z.B. HTML-Fehlerseite eines vorgeschalteten Gateways) - der
    // rohe Body darf nie in die UI durchgereicht werden.
    return `Server antwortet nicht wie erwartet (Status ${response.status}). Bitte in ein paar Minuten erneut versuchen.`;
  }
  return raw;
}

/** Nur noch serverseitig gebraucht (Server Components/Route Handler, die
 * direkt gegen das FastAPI-Backend sprechen): der Auth-Cookie ist httpOnly
 * und daher per document.cookie im Browser gar nicht mehr lesbar - Browser-
 * seitige Aufrufe haengen den Header deshalb nicht mehr selbst an, sondern
 * laufen ueber /api/proxy/... (siehe apiUrl()), das den Cookie server-seitig
 * per next/headers liest und den Authorization-Header dort anhaengt. Der
 * Token verlaesst dadurch nie den Server-Kontext. */
async function authHeader(): Promise<Record<string, string>> {
  if (typeof window === "undefined") {
    const { cookies } = await import("next/headers");
    const token = (await cookies()).get(AUTH_COOKIE_NAME)?.value;
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
  return {};
}

/** Browser-seitige Aufrufe (typeof window !== "undefined") gehen ueber die
 * eigene Next.js-Instanz (/api/proxy/[...path]), die den httpOnly-Cookie
 * server-seitig liest und den Request mit Authorization-Header an das
 * FastAPI-Backend weiterreicht - der Browser spricht dadurch nie direkt mit
 * dem Backend. Server-seitige Aufrufe (Server Components) sprechen weiterhin
 * direkt mit dem Backend, das ist unproblematisch, da der Token dort ohnehin
 * nie den Server verlaesst. */
function apiUrl(path: string): string {
  if (typeof window !== "undefined") return `/api/proxy${path}`;
  if (!API_BASE_URL) throw new Error("NEXT_PUBLIC_CC_CRM_API_URL ist nicht konfiguriert.");
  return `${API_BASE_URL}${path}`;
}

export async function apiGet<T>(path: string, fallback: T): Promise<DataResult<T>> {
  if (DEMO_MODE) return { data: fallback, source: "demo" };

  try {
    const response = await fetch(apiUrl(path), {
      headers: { Accept: "application/json", ...(await authHeader()) },
      // Kein Server-Cache: mit `next: { revalidate: 30 }` lieferte fetch()
      // nach einer Mutation (z.B. router.refresh()) bis zu 30s lang weiter
      // die alte Antwort - neu angelegte/geaenderte Daten erschienen erst
      // nach mehreren manuellen Reloads. Alle Listen-Endpoints antworten
      // ohnehin in <1s (siehe fetchAllPages-Kommentar in queries.ts).
      cache: "no-store",
      signal: timeoutSignal(),
    });
    if (!response.ok) throw new Error(`API antwortet mit ${response.status}`);
    return { data: (await response.json()) as T, source: "api" };
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new Error(`API antwortet nicht innerhalb von ${API_TIMEOUT_MS / 1000}s (${path}).`);
    }
    throw new Error(error instanceof Error ? error.message : "API nicht erreichbar");
  }
}

/** timeoutMs nur fuer bewusst langlaufende Aktionen setzen (z.B. der
 * synchrone Sourcing-Lauf, der pro PLZ einen externen Verzeichnis-Request
 * mit hoeflicher Pause macht) - alle normalen JSON-Endpoints bleiben beim
 * knappen Default-Timeout, damit ein haengendes Backend schnell auffaellt. */
export async function apiPost<T>(path: string, body: unknown, timeoutMs?: number): Promise<T> {
  const effectiveTimeoutMs = timeoutMs ?? API_TIMEOUT_MS;
  try {
    const response = await fetch(apiUrl(path), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...(await authHeader()),
      },
      body: JSON.stringify(body),
      signal: timeoutMs ? AbortSignal.timeout(timeoutMs) : timeoutSignal(),
    });
    if (!response.ok) {
      throw new Error(await errorMessageFromResponse(response));
    }
    return (await response.json()) as T;
  } catch (error) {
    // Ohne diesen Abfang landete ein Timeout als rohe DOMException beim
    // Aufrufer ("signal timed out" o.ae.) statt einer verstaendlichen
    // Meldung - gleiches Muster wie apiGet oben.
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new Error(`API antwortet nicht innerhalb von ${effectiveTimeoutMs / 1000}s (${path}).`);
    }
    throw error;
  }
}

/** Holt eine binaere Antwort als Blob (z.B. fuer eine Dokument-Vorschau).
 * Anders als apiDownload loest das keinen Download aus - der Aufrufer
 * entscheidet, was mit dem Blob passiert (Vorschau via createObjectURL,
 * oder Weiterreichen an apiDownload-artiges Speichern). */
export async function apiFetchBlob(path: string): Promise<Blob> {
  const response = await fetch(apiUrl(path), {
    headers: { ...(await authHeader()) },
    // Datei-Transfers duerfen laenger dauern als eine normale JSON-Antwort,
    // sollen aber ebenfalls nicht unbegrenzt haengen koennen.
    signal: AbortSignal.timeout(60_000),
  });
  if (!response.ok) {
    throw new Error(await errorMessageFromResponse(response));
  }
  return response.blob();
}

/** Downloads a binary response (e.g. a generated .docx) and triggers a browser
 * save-as via a synthetic link click. Not used for JSON endpoints. */
export async function apiDownload(path: string, filename: string): Promise<void> {
  const blob = await apiFetchBlob(path);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** Uploads a file as multipart/form-data (e.g. document upload). Do not set
 * Content-Type manually - the browser needs to add the multipart boundary. */
export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "POST",
    headers: { Accept: "application/json", ...(await authHeader()) },
    body: formData,
    // Datei-Uploads duerfen laenger dauern als eine normale JSON-Anfrage,
    // sollen aber ebenfalls nicht unbegrenzt haengen koennen.
    signal: AbortSignal.timeout(60_000),
  });
  if (!response.ok) {
    throw new Error(await errorMessageFromResponse(response));
  }
  return response.json() as Promise<T>;
}

export async function apiDelete(path: string): Promise<void> {
  const response = await fetch(apiUrl(path), {
    method: "DELETE",
    headers: { Accept: "application/json", ...(await authHeader()) },
    signal: timeoutSignal(),
  });
  if (!response.ok) {
    throw new Error(await errorMessageFromResponse(response));
  }
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(await authHeader()),
    },
    body: JSON.stringify(body),
    signal: timeoutSignal(),
  });
  if (!response.ok) {
    throw new Error(await errorMessageFromResponse(response));
  }
  return response.json() as Promise<T>;
}
