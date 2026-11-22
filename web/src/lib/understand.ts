/**
 * Free-text understanding, as the backend's /api/ask does it (backend/nlu.py,
 * same lexicon). The live app asks the backend, which can also consult a
 * Databricks-hosted language model; demo mode runs these same rules here.
 *
 * Rules first: red flags are screened before anything else, and an emergency
 * score of 80+ goes straight to the emergency screen. Every care, place and
 * urgency finding carries the person's exact words (start/end in their text),
 * so the page can show what each one rests on.
 */
import { careTerms, lexicon } from "../data/careTerms";
import type { AskResponse, AskSpan } from "../types";

const URGENCY_SCORE = { 1: 100, 2: 85, 3: 60, 4: 15 } as const;
const URGENCY_LABEL = { 1: "life-threatening", 2: "emergency", 3: "urgent", 4: "not urgent" } as const;
export const EMERGENCY_SCORE_MIN = 80;

const DEVANAGARI = /[\u0900-\u097F]/;
const CLAUSE_BREAK = /[.,;:!?।\n]|\bbut\b|\bhowever\b|\balthough\b|\bthough\b|\blekin\b|लेकिन|मगर/gi;
const EN_DENIAL =
  /(?:\bno|\bnot|\bwithout|\bdenies|\bdenied|n't|\bnever|\bnone)(?:\s+(?:any|a|an|the|signs?|of|more|longer|real|other|having|experiencing|feeling|have|has|had|been|is|was|felt|got|much|serious|major|really))*\s*$/i;
const HI_DENIAL_AFTER = /^\s*(?:(?:है|था|थी|हैं|तो|बिल्कुल|कोई|hai|tha|thi|to)\s*)?(?:नहीं|नही|nahi|nahin|nai\b)/i;

function clauseBounds(text: string, start: number, end: number): [number, number] {
  let lo = 0;
  for (const m of text.slice(0, start).matchAll(CLAUSE_BREAK)) lo = (m.index ?? 0) + m[0].length;
  const rest = new RegExp(CLAUSE_BREAK.source, "gi");
  rest.lastIndex = end;
  const next = rest.exec(text);
  return [lo, next ? next.index : text.length];
}

/** True when the person explicitly denies text[start:end] in its own clause ("no chest pain"). */
export function isDenied(text: string, start: number, end: number): boolean {
  const [lo, hi] = clauseBounds(text, start, end);
  return EN_DENIAL.test(text.slice(lo, start)) || HI_DENIAL_AFTER.test(text.slice(end, hi));
}

function escape(phrase: string) {
  return phrase.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/ /g, "\\s+");
}

function phraseRegex(phrase: string) {
  return DEVANAGARI.test(phrase)
    ? new RegExp(escape(phrase), "g")
    : new RegExp(`(?<![a-z0-9])${escape(phrase)}(?![a-z0-9])`, "g");
}

const flags = lexicon.redFlags.map((flag) => ({
  ...flag,
  regexes: flag.patterns.map((pattern) => new RegExp(pattern, "giu")),
}));
const terms = careTerms
  .flatMap((term) => term.say.map((phrase) => ({ key: term.id, phrase, rx: phraseRegex(phrase) })))
  .sort((a, b) => b.phrase.length - a.phrase.length);
const broad = lexicon.broad
  .flatMap((item) => item.say.map((phrase) => ({ key: item.options, phrase, rx: phraseRegex(phrase) })))
  .sort((a, b) => b.phrase.length - a.phrase.length);
const hereCues = lexicon.placeCuesHere.map((pattern) => new RegExp(pattern, "iu"));
const placesHi = Object.entries(lexicon.placesHi).sort((a, b) => b[0].length - a[0].length);
const stop = new Set([
  ...lexicon.placeStopwords,
  ...terms.filter((t) => !DEVANAGARI.test(t.phrase)).flatMap((t) => t.phrase.split(" ")),
]);
const hiNonPlaces = new Set(lexicon.hiNonPlaces);

function matches<K>(text: string, table: Array<{ key: K; rx: RegExp }>) {
  const low = text.toLowerCase();
  const taken: Array<[number, number]> = [];
  const hits: Array<{ key: K; span: AskSpan }> = [];
  for (const { key, rx } of table) {
    for (const m of low.matchAll(rx)) {
      const s = m.index ?? 0;
      const e = s + m[0].length;
      if (taken.some(([ts, te]) => s < te && ts < e) || isDenied(text, s, e)) continue;
      taken.push([s, e]);
      hits.push({ key, span: { quote: text.slice(s, e), start: s, end: e } });
    }
  }
  return hits;
}

const PREP =
  /(?<![a-z])(?:near|in|at|around|close to|from|next to|nearest to)\s+([a-z][a-z .'-]{1,40}?)(?=\s*(?:[,.;!?।]|$|\b(?:for|with|who|which|that|because|please|asap|urgently|today|tomorrow|tonight|now|and|hospital|hospitals|area|district|city)\b))/gi;
const HINGLISH = /([a-z]+(?:\s[a-z]+)?)\s+(?:ke paas|ke pass|ke nazdeek|ke najdeek|ke aas ?paas|mein|me)\b/gi;
const HINDI = /([\u0900-\u097F]+(?:\s[\u0900-\u097F]+)?)\s+(?:के पास|के नज़दीक|के नजदीक|के आसपास|के आस-पास|में|से)/g;
const PIN = /(?<!\d)\d{6}(?!\d)/;

function titleCase(name: string) {
  return /^[a-z .'-]+$/.test(name) ? name.replace(/\b[a-z]/g, (c) => c.toUpperCase()) : name;
}

type Place = NonNullable<AskResponse["place"]>;

function extractPlace(text: string, knownPlace: (name: string) => boolean): Place | null {
  const found = (name: string, s: number, e: number): Place => ({
    text: titleCase(name),
    here: false,
    source: "rules",
    span: { quote: text.slice(s, e), start: s, end: e },
  });
  const pin = PIN.exec(text);
  if (pin) return found(pin[0], pin.index, pin.index + 6);
  for (const [hi, en] of placesHi) {
    const i = text.indexOf(hi);
    if (i >= 0) return { ...found(en, i, i + hi.length), text: en };
  }
  for (const rx of [PREP, HINGLISH]) {
    for (const m of text.matchAll(rx)) {
      const words = m[1].trim().replace(/^[ .'-]+|[ .'-]+$/g, "").split(/\s+/).filter(Boolean);
      while (words.length && stop.has(words[0].toLowerCase())) words.shift();
      while (words.length && stop.has(words[words.length - 1].toLowerCase())) words.pop();
      for (let n = words.length; n > 0; n -= 1) {
        const name = words.slice(0, n).join(" ");
        if (knownPlace(name) || (rx === PREP && n === words.length)) {
          const base = (m.index ?? 0) + m[0].indexOf(m[1]);
          const s = base + m[1].indexOf(words[0]);
          const e = base + m[1].indexOf(words[n - 1]) + words[n - 1].length;
          return found(name, s, e);
        }
      }
    }
  }
  for (const m of text.matchAll(HINDI)) {
    const words = m[1].split(/\s+/).filter((w) => !hiNonPlaces.has(w));
    if (words.length && knownPlace(words.join(" "))) {
      const s = m.index ?? 0;
      return found(words.join(" "), s, s + m[1].length);
    }
  }
  const tokens = [...text.matchAll(/[A-Za-z][A-Za-z.'-]+/g)];
  for (const n of [2, 1]) {
    for (let i = 0; i + n <= tokens.length; i += 1) {
      const group = tokens.slice(i, i + n);
      const name = group.map((t) => t[0]).join(" ");
      if (!stop.has(name.toLowerCase()) && knownPlace(name)) {
        const last = group[group.length - 1];
        return found(name, group[0].index ?? 0, (last.index ?? 0) + last[0].length);
      }
    }
  }
  for (const rx of hereCues) {
    const m = rx.exec(text);
    if (m && !isDenied(text, m.index, m.index + m[0].length)) {
      return {
        text: null,
        here: true,
        source: "rules",
        span: { quote: m[0], start: m.index, end: m.index + m[0].length },
      };
    }
  }
  return null;
}

const careRef = (id: string) => {
  const term = careTerms.find((t) => t.id === id);
  return { id, name: term?.en ?? id, nameHi: term?.hi ?? id };
};

/** The rules half of /api/ask: urgency, care and place, each with the person's own words. */
export function understand(rawText: string, knownPlace: (name: string) => boolean): Omit<AskResponse, "next"> {
  const text = rawText.trim();
  let level: 1 | 2 | 3 | 4 = 4;
  let rule: string | null = null;
  let urgencySpan: AskSpan | undefined;
  let crisis = false;
  for (const flag of flags) {
    for (const rx of flag.regexes) {
      let hit = false;
      for (const m of text.matchAll(rx)) {
        const s = m.index ?? 0;
        if (isDenied(text, s, s + m[0].length)) continue;
        if (flag.level < level) {
          level = flag.level;
          rule = flag.id;
          urgencySpan = { quote: m[0], start: s, end: s + m[0].length };
        }
        crisis = crisis || Boolean(flag.crisis);
        hit = true;
        break;
      }
      if (hit) break;
    }
  }
  const score = URGENCY_SCORE[level];
  const place = extractPlace(text, knownPlace);
  const base = {
    text,
    method: "rules" as const,
    llm: { used: false },
    urgency: {
      level,
      score,
      label: URGENCY_LABEL[level],
      rule,
      source: rule ? ("rules" as const) : ("none" as const),
      crisis,
      emergency: score >= EMERGENCY_SCORE_MIN,
      ...(urgencySpan ? { span: urgencySpan } : {}),
    },
    place,
    care: null as AskResponse["care"],
    careOptions: [] as AskResponse["careOptions"],
  };
  if (base.urgency.emergency) return base;
  const hits = matches(text, terms).sort((a, b) => b.span.end - b.span.start - (a.span.end - a.span.start));
  if (hits.length) {
    return { ...base, care: { ...careRef(hits[0].key), source: "rules", span: hits[0].span } };
  }
  const wide = matches(text, broad);
  if (wide.length) {
    return { ...base, careOptions: wide[0].key.map(careRef), careOptionsSpan: wide[0].span };
  }
  return base;
}
