import { useSyncExternalStore } from "react";
import { profileSnapshot, replaceProfile, type Profile } from "./profile";
import { createStore } from "./store";

/**
 * Sign-in with a mobile number and a one-time code — how most people in India
 * already sign in to everything.
 *
 * `AuthClient` is the seam for the real backend: swap `demoAuth` for a client
 * that calls the API's OTP endpoints and nothing else changes. The demo client
 * sends no SMS; it accepts the code 123456 and keeps the "account" in this
 * browser, so the flow can be tried end to end. The UI says so.
 */
export interface Session {
  /** 10-digit mobile number, digits only. */
  phone: string;
  signedInAt: string;
}

export interface AuthClient {
  readonly isDemo: boolean;
  /** Sends a code; resolves with seconds until a resend is allowed. */
  requestOtp(phone: string): Promise<{ resendAfterSeconds: number }>;
  /** Checks the code; resolves with the account's saved profile, if any. */
  verifyOtp(phone: string, code: string): Promise<{ session: Session; savedProfile: Profile | null }>;
  /** Copies the device profile to the account. */
  saveProfile(session: Session, profile: Profile): Promise<void>;
}

export class AuthError extends Error {
  constructor(public code: "invalid_phone" | "wrong_code" | "network") {
    super(code);
  }
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));
const accountKey = (phone: string) => `carepath.demo-account.${phone}`;

export const DEMO_CODE = "123456";

export const demoAuth: AuthClient = {
  isDemo: true,
  async requestOtp(phone) {
    await wait(500);
    if (!/^[6-9]\d{9}$/.test(phone)) throw new AuthError("invalid_phone");
    return { resendAfterSeconds: 30 };
  },
  async verifyOtp(phone, code) {
    await wait(500);
    if (code !== DEMO_CODE) throw new AuthError("wrong_code");
    let savedProfile: Profile | null = null;
    try {
      const raw = window.localStorage.getItem(accountKey(phone));
      savedProfile = raw ? (JSON.parse(raw) as Profile) : null;
    } catch {
      savedProfile = null;
    }
    return { session: { phone, signedInAt: new Date().toISOString() }, savedProfile };
  },
  async saveProfile(session, profile) {
    try {
      window.localStorage.setItem(accountKey(session.phone), JSON.stringify(profile));
    } catch {
      /* demo only */
    }
  },
};

export const auth: AuthClient = demoAuth;

const sessionStore = createStore<Session | null>("carepath.session.v1", null, (raw) => {
  const value = raw as Partial<Session> | null;
  return value && typeof value.phone === "string" && typeof value.signedInAt === "string"
    ? { phone: value.phone, signedInAt: value.signedInAt }
    : null;
});

export function useSession() {
  return useSyncExternalStore(sessionStore.subscribe, sessionStore.snapshot, () => null);
}

/**
 * Finish sign-in: answers given on this device win over older account values,
 * and the merged result is written back to the account.
 */
export async function completeSignIn(session: Session, savedProfile: Profile | null) {
  const local = profileSnapshot();
  const merged: Profile = savedProfile
    ? {
        ...savedProfile,
        ...Object.fromEntries(Object.entries(local).filter(([, value]) => value !== null && value !== false)),
      }
    : local;
  replaceProfile(merged);
  sessionStore.write(session);
  await auth.saveProfile(session, merged);
}

export function signOut() {
  sessionStore.write(null);
}

/** "+91 98765 43210", or masked: "+91 98••• ••210". */
export function formatPhone(digits: string, masked = false) {
  if (masked) return `+91 ${digits.slice(0, 2)}••• ••${digits.slice(7)}`;
  return `+91 ${digits.slice(0, 5)} ${digits.slice(5)}`;
}

/**
 * Only same-site relative paths are allowed as a return address, so a crafted
 * link can't bounce someone to another site after they sign in.
 */
export function safeReturnTo(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/";
  try {
    const url = new URL(value, "https://carepath.local");
    if (url.origin !== "https://carepath.local") return "/";
    if (url.pathname === "/sign-in") return "/";
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return "/";
  }
}
