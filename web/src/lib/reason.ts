import type { ConfidenceLevel, SourceType } from "../types";

/**
 * The line on each result that says whether the service is confirmed, and
 * the one-word status used on the shorter rows.
 *
 * Only sources we can name count as confirmation: the hospital's own website,
 * a government listing, a directory, or social media. A page the recommender
 * could not classify ("unknown") is never presented as confirmation.
 *
 * Advice only names an action the card can actually offer: "Call" when there
 * is a number to call, "Check the website" when there is only a website, and
 * otherwise a plain description with no instruction.
 */
export interface ReasonCopy {
  reasonHigh: (sources: string) => string;
  reasonMedium: string;
  reasonLow: string;
  reasonWebOnly: string;
  actionCall: string;
  actionWebsite: string;
  and: string;
  srcListOfficial: string;
  srcListGovernment: string;
  srcListDirectory: string;
  srcListSocial: string;
  statusConfirmed: string;
  statusCheck: string;
  statusCheckWebsite: string;
  statusPartly: string;
  statusNot: string;
}

export interface Contact {
  phone?: string | null;
  website?: string | null;
}

// Strongest first, so the two named are the two that matter most.
const CONFIRMING: Array<Exclude<SourceType, "unknown">> = ["official_site", "government", "directory", "social_media"];

function action(copy: ReasonCopy, contact: Contact) {
  if (contact.phone) return copy.actionCall;
  if (contact.website) return copy.actionWebsite;
  return "";
}

export function reasonText(
  copy: ReasonCopy,
  confidence: ConfidenceLevel,
  sourceTypes: SourceType[],
  contact: Contact = {},
): { text: string; confirmed: boolean } {
  const withAction = (base: string) => [base, action(copy, contact)].filter(Boolean).join(" ");
  if (confidence === "medium") return { text: withAction(copy.reasonMedium), confirmed: false };
  if (confidence === "low") return { text: withAction(copy.reasonLow), confirmed: false };
  const names: Record<Exclude<SourceType, "unknown">, string> = {
    official_site: copy.srcListOfficial,
    government: copy.srcListGovernment,
    directory: copy.srcListDirectory,
    social_media: copy.srcListSocial,
  };
  const known = CONFIRMING.filter((kind) => sourceTypes.includes(kind)).slice(0, 2);
  if (known.length === 0) return { text: withAction(copy.reasonWebOnly), confirmed: false };
  return { text: copy.reasonHigh(known.map((kind) => names[kind]).join(` ${copy.and} `)), confirmed: true };
}

/** One word or two for a short row: what the card's own buttons let you do. */
export function statusLabel(copy: ReasonCopy, level: "high" | "medium" | "low", contact: Contact) {
  if (level === "high") return copy.statusConfirmed;
  if (contact.phone) return copy.statusCheck;
  if (contact.website) return copy.statusCheckWebsite;
  return level === "low" ? copy.statusNot : copy.statusPartly;
}

/** Ownership worth showing; "Unknown" (or empty) is left off the card. */
export function knownOperator(operator: string | undefined | null) {
  const value = (operator ?? "").trim();
  return value && value.toLowerCase() !== "unknown" ? value : null;
}
