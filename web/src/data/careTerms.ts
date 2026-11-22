/**
 * The 100 kinds of care Annu knows (ids match the backend's service tags,
 * data/tags/service_tags.json), with a Hindi name and the everyday words people
 * use for each: English, Hindi and Hinglish (Hindi typed in Latin letters).
 *
 * `say` lists phrases that name the care or plainly describe needing it. They
 * are matched as whole words, longest first, so "kidney transplant" wins over
 * "kidney". Phrases are not symptoms to diagnose from: "chest pain" is not
 * here, it is a red flag (lib/understand.ts) and goes straight to 108.
 *
 * `ask` marks a broad word that fits several kinds of care; Raahi then asks
 * which one, instead of guessing.
 */
import lexiconJson from "./lexicon.json";

export interface CareTerm {
  id: string;
  en: string;
  hi: string;
  say: string[];
}

export interface BroadTerm {
  say: string[];
  options: string[];
}

export interface RedFlag {
  id: string;
  /** 1 life-threatening now, 2 emergency (both open the emergency screen), 3 urgent. */
  level: 1 | 2 | 3;
  crisis?: boolean;
  patterns: string[];
}

/** Shared with the backend (backend/nlu.py reads the same file). */
export interface Lexicon {
  terms: CareTerm[];
  broad: BroadTerm[];
  redFlags: RedFlag[];
  placeCuesHere: string[];
  placesHi: Record<string, string>;
  placeStopwords: string[];
  hiNonPlaces: string[];
}

export const lexicon = lexiconJson as Lexicon;
export const careTerms = lexicon.terms;
/**
 * Broad words that fit several kinds of care. Raahi asks which one; it never
 * picks for the person.
 */
export const broadTerms = lexicon.broad;

const byId = new Map(careTerms.map((term) => [term.id, term]));

export function careTerm(id: string): CareTerm | undefined {
  return byId.get(id);
}

/** The care's name in the page language, or the given English name when the id is unknown. */
export function careName(id: string | undefined, lang: "en" | "hi", fallback: string): string {
  const term = id ? byId.get(id) : undefined;
  if (!term) return fallback;
  return lang === "hi" ? term.hi : term.en;
}
