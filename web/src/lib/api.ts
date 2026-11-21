import type { LocationOption, RecommendationResponse, ServiceOption } from "../types";
import { getDemoRecommendations } from "./demoApi";
import { locations as demoLocations, services as demoServices } from "../data/demo";

/** Backend base URL. Empty = same origin (Vite dev server proxies /api to the FastAPI backend). */
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
/** Set VITE_USE_DEMO=true to run the UI on the bundled mock data without a backend. */
export const USE_DEMO = import.meta.env.VITE_USE_DEMO === "true";

/** The only user inputs: the service and the location ("Use my location" fills the location as coordinates). */
export interface SearchInput {
  serviceText: string;
  locationText: string;
  coordinates?: { latitude: number; longitude: number };
}

export class ApiError extends Error {
  field?: "service" | "location";
  suggestions: string[];
  constructor(message: string, field?: "service" | "location", suggestions: string[] = []) {
    super(message);
    this.field = field;
    this.suggestions = suggestions;
  }
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
