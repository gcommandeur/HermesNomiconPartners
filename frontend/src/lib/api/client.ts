import type { DataResult } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_CC_CRM_API_URL?.replace(/\/$/, "");
const DEMO_MODE = process.env.NEXT_PUBLIC_CC_CRM_DEMO_MODE === "true";
export const apiBaseUrl = API_BASE_URL;
export const AUTH_COOKIE_NAME = "cc_crm_token";

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

function readBrowserCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/** FastAPI error responses are JSON like {"detail": "..."}; showing that raw
 * in the UI ("{"detail":"..."}") looks broken. Extract just the message. */
async function errorMessageFromResponse(response: Response): Promise<string> {
  const raw = await response.text();
  if (!raw) return `API antwortet mit ${response.status}`;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // not JSON - fall through to raw text
  }
  return raw;
}

async function authHeader(): Promise<Record<string, string>> {
  if (typeof window === "undefined") {
    const { cookies } = await import("next/headers");
    const token = (await cookies()).get(AUTH_COOKIE_NAME)?.value;
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
  const token = readBrowserCookie(AUTH_COOKIE_NAME);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiGet<T>(path: string, fallback: T): Promise<DataResult<T>> {
  if (DEMO_MODE) return { data: fallback, source: "demo" };
  if (!API_BASE_URL) throw new Error("NEXT_PUBLIC_CC_CRM_API_URL ist nicht konfiguriert.");

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
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

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  if (!API_BASE_URL) throw new Error("API-URL ist nicht konfiguriert.");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
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

/** Holt eine binaere Antwort als Blob (z.B. fuer eine Dokument-Vorschau).
 * Anders als apiDownload loest das keinen Download aus - der Aufrufer
 * entscheidet, was mit dem Blob passiert (Vorschau via createObjectURL,
 * oder Weiterreichen an apiDownload-artiges Speichern). */
export async function apiFetchBlob(path: string): Promise<Blob> {
  if (!API_BASE_URL) throw new Error("API-URL ist nicht konfiguriert.");
  const response = await fetch(`${API_BASE_URL}${path}`, {
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
  if (!API_BASE_URL) throw new Error("API-URL ist nicht konfiguriert.");
  const response = await fetch(`${API_BASE_URL}${path}`, {
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
  if (!API_BASE_URL) throw new Error("API-URL ist nicht konfiguriert.");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "DELETE",
    headers: { Accept: "application/json", ...(await authHeader()) },
    signal: timeoutSignal(),
  });
  if (!response.ok) {
    throw new Error(await errorMessageFromResponse(response));
  }
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  if (!API_BASE_URL) throw new Error("API-URL ist nicht konfiguriert.");
  const response = await fetch(`${API_BASE_URL}${path}`, {
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
