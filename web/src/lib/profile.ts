import { useSyncExternalStore } from "react";
import { createStore } from "./store";

/**
 * What Annu remembers about the person: only answers that change their
 * results or their emergency screen. Distance and government preferences
 * are applied in the browser on top of the recommender's own results. Nothing medical, no scheme or income
 * details. Kept on this device; signing in copies it to their account.
 */
export interface EmergencyContact {
  name: string;
  /** 10-digit Indian mobile number, digits only. */
  phone: string;
}

export interface Profile {
  /** Default search place, e.g. "Bhubaneswar, Odisha". */
  location: string | null;
  /** List government hospitals before private ones. */
  governmentFirst: boolean | null;
  emergencyContact: EmergencyContact | null;
  /** Finished or skipped the welcome steps; either way, don't offer again. */
  onboardingDone: boolean;
  /** Dismissed the "set up" line on the home page. */
  promptDismissed: boolean;
}

export const emptyProfile: Profile = {
  location: null,
  governmentFirst: null,
  emergencyContact: null,
  onboardingDone: false,
  promptDismissed: false,
};

export function isValidMobile(digits: string) {
  return /^[6-9]\d{9}$/.test(digits);
}

function parse(raw: unknown): Profile {
  if (!raw || typeof raw !== "object") return emptyProfile;
  const value = raw as Record<string, unknown>;
  const contact = value.emergencyContact as Record<string, unknown> | null | undefined;
  return {
    location: typeof value.location === "string" ? value.location.slice(0, 80) : null,
    governmentFirst: typeof value.governmentFirst === "boolean" ? value.governmentFirst : null,
    emergencyContact:
      contact &&
      typeof contact.name === "string" &&
      typeof contact.phone === "string" &&
      isValidMobile(contact.phone)
        ? { name: contact.name.slice(0, 40), phone: contact.phone }
        : null,
    onboardingDone: value.onboardingDone === true,
    promptDismissed: value.promptDismissed === true,
  };
}

const store = createStore<Profile>("annu.profile.v1", emptyProfile, parse);

export function profileSnapshot() {
  return store.snapshot();
}

export function saveProfile(patch: Partial<Profile>): Profile {
  const next = { ...store.snapshot(), ...patch };
  store.write(next);
  return next;
}

export function replaceProfile(next: Profile) {
  store.write(next);
}

export function useProfile(): Profile {
  return useSyncExternalStore(store.subscribe, store.snapshot, () => emptyProfile);
}
