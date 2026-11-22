import type { ConfidenceLevel, SourceType } from "../types";

/**
 * The one line on each result that says whether the service is confirmed.
 *
 * Only sources we can name count as confirmation: the hospital's own website,
 * a government listing, a directory, or social media. A page the recommender
 * could not classify ("unknown") is never presented as confirmation; when it
 * is all there is, the line says the service is mentioned on public web
 * pages and asks the person to call first.
 */
export interface ReasonCopy {
  reasonHigh: (sources: string) => string;
  reasonMedium: string;
  reasonLow: string;
  reasonWebOnly: string;
  and: string;
  srcListOfficial: string;
  srcListGovernment: string;
  srcListDirectory: string;
  srcListSocial: string;
}

// Strongest first, so the two named are the two that matter most.
const CONFIRMING: Array<Exclude<SourceType, "unknown">> = ["official_site", "government", "directory", "social_media"];

export function reasonText(
  copy: ReasonCopy,
  confidence: ConfidenceLevel,
  sourceTypes: SourceType[],
): { text: string; confirmed: boolean } {
  if (confidence === "medium") return { text: copy.reasonMedium, confirmed: false };
  if (confidence === "low") return { text: copy.reasonLow, confirmed: false };
  const names: Record<Exclude<SourceType, "unknown">, string> = {
    official_site: copy.srcListOfficial,
    government: copy.srcListGovernment,
    directory: copy.srcListDirectory,
    social_media: copy.srcListSocial,
  };
  const known = CONFIRMING.filter((kind) => sourceTypes.includes(kind)).slice(0, 2);
  if (known.length === 0) return { text: copy.reasonWebOnly, confirmed: false };
  return { text: copy.reasonHigh(known.map((kind) => names[kind]).join(` ${copy.and} `)), confirmed: true };
}

/** Ownership worth showing; "Unknown" (or empty) is left off the card. */
export function knownOperator(operator: string | undefined | null) {
  const value = (operator ?? "").trim();
  return value && value.toLowerCase() !== "unknown" ? value : null;
}
