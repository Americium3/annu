import type { AskResponse, LocationOption, RecommendationResponse, ServiceOption } from "../types";
import { askDemo, getDemoRecommendations } from "./demoApi";
import { ApiError } from "./errors";

export { ApiError };
import { locations as demoLocations, services as demoServices } from "../data/demo";

/** Backend base URL. Empty = same origin (Vite dev server proxies /api to the FastAPI backend). */
export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
/** Set VITE_USE_DEMO=true to run the UI on the bundled mock data without a backend. */
export const USE_DEMO = import.meta.env.VITE_USE_DEMO === "true";

/** A structured search: the service and the location ("Use my location" fills the location as coordinates),
 * plus the urgency level /api/ask found in the person's words (3 = nearer hospitals count more). */
export interface SearchInput {
  serviceText: string;
  locationText: string;
  coordinates?: { latitude: number; longitude: number };
  urgency?: number;
  /** Ask the language model to judge the top hospitals' records (slower; live data only). */
  judge?: boolean;
}

/** A free-text request. The saved place / device location is used only when the text names no place. */
export interface AskInput {
  text: string;
  locationText?: string;
  coordinates?: { latitude: number; longitude: number };
}

// Right after a (re)deploy the server spends a minute or two loading the hospital data and answers 503
// ("Loading live hospital data"). The page waits and asks again instead of giving up, for up to this long.
const WARMUP_WAIT_MS = 180_000;
const WARMUP_POLL_MS = 4000;

function warmingUp(response: Response) {
  return (response.status === 503 && response.headers.has("Retry-After")) || response.status === 502;
}

async function request<T>(path: string, init?: RequestInit, onWaiting?: () => void): Promise<T> {
  const started = Date.now();
  let told = false;
  for (;;) {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}${path}`, {
        ...init,
        headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      });
    } catch {
      throw new ApiError("Cannot reach the Annu API. Is the backend running on port 8000?");
    }
    if (!response.ok && warmingUp(response) && Date.now() - started < WARMUP_WAIT_MS) {
      if (!told) {
        told = true;
        onWaiting?.();
      }
      await new Promise((done) => setTimeout(done, WARMUP_POLL_MS));
      continue;
    }
    if (!response.ok) {
      const body = await response.json().catch(() => undefined);
      const detail = body?.detail;
      if (detail && typeof detail === "object" && "message" in detail) {
        throw new ApiError(detail.message, detail.field, detail.suggestions ?? []);
      }
      throw new ApiError(`Request failed (${response.status}).`);
    }
    return (await response.json()) as T;
  }
}

export async function getRecommendations(input: SearchInput, onWaiting?: () => void): Promise<RecommendationResponse> {
  if (USE_DEMO) return getDemoRecommendations(input);
  return request<RecommendationResponse>("/api/recommendations", { method: "POST", body: JSON.stringify(input) }, onWaiting);
}

/** `onWaiting` is called once if the server is still loading its data and the page is waiting for it. */
export async function ask(input: AskInput, onWaiting?: () => void): Promise<AskResponse> {
  if (USE_DEMO) return askDemo(input);
  return request<AskResponse>("/api/ask", { method: "POST", body: JSON.stringify(input) }, onWaiting);
}

export async function fetchServices(): Promise<ServiceOption[]> {
  if (USE_DEMO) return demoServices;
  return request<ServiceOption[]>("/api/services");
}

export async function fetchLocations(query: string): Promise<LocationOption[]> {
  if (USE_DEMO) {
    const q = query.toLowerCase();
    return demoLocations.filter((l) => `${l.name} ${l.region}`.toLowerCase().includes(q));
  }
  if (!query.trim()) return [];
  return request<LocationOption[]>(`/api/locations?q=${encodeURIComponent(query)}`);
}
