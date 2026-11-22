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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("Cannot reach the CarePath API. Is the backend running on port 8000?");
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

export async function getRecommendations(input: SearchInput): Promise<RecommendationResponse> {
  if (USE_DEMO) return getDemoRecommendations(input);
  return request<RecommendationResponse>("/api/recommendations", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function ask(input: AskInput): Promise<AskResponse> {
  if (USE_DEMO) return askDemo(input);
  return request<AskResponse>("/api/ask", { method: "POST", body: JSON.stringify(input) });
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
