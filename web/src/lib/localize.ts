/**
 * Hindi for what comes from the data rather than from the page's own copy:
 * care names (by tag id), city names, hospital types and the recommender's
 * notes. Hospital names and addresses are proper nouns and stay as written;
 * quotes from sources stay in their original language (they are the proof).
 */
import { careName, lexicon } from "../data/careTerms";
import type { Lang } from "../i18n";
import type { RecommendationResponse } from "../types";

const placeHi = new Map(Object.entries(lexicon.placesHi).map(([hi, en]) => [en.toLowerCase(), hi]));

/** "Cuttack" → "कटक" on Hindi pages, when we know the name; otherwise as given. */
export function placeName(name: string, lang: Lang): string {
  if (lang !== "hi") return name;
  const [head, ...rest] = name.split(",");
  const hi = placeHi.get(head.trim().toLowerCase());
  return hi ? [hi, ...rest].join(",") : name;
}

export function serviceName(data: RecommendationResponse, lang: Lang): string {
  const service = data.queryContext.service;
  return careName(service.canonicalId, lang, service.displayName);
}

/** Where the search was measured from, in the page language. */
export function searchedFrom(data: RecommendationResponse, lang: Lang, current: string): string {
  const location = data.queryContext.location;
  return location.type === "coordinates" ? current : placeName(location.resolvedName, lang);
}

const TYPE_HI: Array<[RegExp, string]> = [
  [/multi[- ]?speciality|multi[- ]?specialty/i, "मल्टीस्पेशियलिटी अस्पताल"],
  [/super[- ]?speciality|super[- ]?specialty/i, "सुपर-स्पेशियलिटी अस्पताल"],
  [/speciality|specialty/i, "स्पेशियलिटी अस्पताल"],
  [/teaching|medical college/i, "मेडिकल कॉलेज अस्पताल"],
  [/district hospital/i, "ज़िला अस्पताल"],
  [/community health/i, "सामुदायिक स्वास्थ्य केंद्र"],
  [/primary health/i, "प्राथमिक स्वास्थ्य केंद्र"],
  [/nursing home/i, "नर्सिंग होम"],
  [/dental/i, "दाँतों का क्लिनिक"],
  [/diagnostic|imaging|lab/i, "जाँच केंद्र"],
  [/clinic/i, "क्लिनिक"],
  [/general hospital|^hospital$/i, "अस्पताल"],
  [/hospital/i, "अस्पताल"],
];

export function facilityType(type: string, lang: Lang): string {
  if (lang !== "hi" || !type) return type;
  return TYPE_HI.find(([rx]) => rx.test(type))?.[1] ?? type;
}

/** The recommender's notes (backend and demo) in Hindi; unknown notes stay as written. */
export function localizeWarning(warning: string, lang: Lang, service: string): string {
  if (lang !== "hi") return warning;
  let m = warning.match(
    /^(\d+) facilities in the dataset list .+? \((\d+) with usable evidence and location\); (\d+) within (\d+) km; (\d+) more within/,
  );
  if (m) {
    return `डेटा में ${m[1]} जगहें ${service} देती बताई गई हैं (${m[2]} के सबूत और लोकेशन काम के हैं)। ${m[4]} किमी के भीतर ${m[3]}; ${m[5]} और की जाँच अधूरी है, इसलिए नहीं दिखाईं।`;
  }
  m = warning.match(/^No listed provider within (\d+) km; search widened to (\d+) km/);
  if (m) return `${m[1]} किमी के भीतर कोई नहीं मिला, इसलिए ${m[2]} किमी तक खोजा।`;
  m = warning.match(/^No facility within (\d+) km lists .+? with usable evidence\.(?: The nearest one in the dataset is about (\d+) km away\.)?/);
  if (m) {
    return `${m[1]} किमी के भीतर किसी अस्पताल के पास ${service} का पक्का सबूत नहीं मिला।${
      m[2] ? ` सबसे पास वाला करीब ${m[2]} किमी दूर है।` : ""
    } इसका मतलब यह नहीं कि इलाके में यह सेवा नहीं है।`;
  }
  m = warning.match(/^Location is ambiguous: .*Using (.+?)\.$/);
  if (m) return `जगह के एक से ज़्यादा मतलब हो सकते हैं; ${placeName(m[1], lang)} मानकर खोजा।`;
  if (/^Service evidence is text extracted/.test(warning)) {
    return "सेवा के सबूत सार्वजनिक वेबपेजों से लिए गए हैं: जाने से पहले अस्पताल से पुष्टि करें।";
  }
  if (/^Demo data only/.test(warning)) return "सिर्फ़ डेमो डेटा: अस्पतालों के नाम और स्रोत उदाहरण हैं।";
  if (/demo dataset|demo evidence/.test(warning)) return "यह डेमो सबूत है, असली इलाज के फ़ैसले के लिए नहीं।";
  return warning;
}

const UNSURE_HI: Record<string, string> = {
  ONLY_EQUIPMENT_EVIDENCE: "सबूत में सिर्फ़ उपकरण का ज़िक्र है, सेवा का नहीं।",
  SINGLE_STATEMENT: "सिर्फ़ एक बयान में इस इलाज का ज़िक्र है।",
  COORDINATES_UNVERIFIED: "नक्शे की लोकेशन पिन कोड से मिलाई नहीं जा सकी।",
  PIN_AREA_ONLY: "अस्पताल की जगह सिर्फ़ पिन कोड के इलाके तक पता है।",
  MENTIONS_OTHER_INSTITUTION: "कुछ बयानों में किसी दूसरी संस्था का भी नाम है।",
  POSSIBLE_DUPLICATE: "इसी नाम और शहर का एक और रिकॉर्ड है।",
  LIST_TRUNCATED: "स्रोत की सूची लंबी थी और अधूरी हो सकती है।",
  NO_CONTACT: "पुष्टि के लिए डेटा में फ़ोन या वेबसाइट नहीं है।",
  STALE_SOURCE: "कुछ जानकारी पुराने या दूसरे स्रोतों से है।",
  SERVICE_ONLY_IN_FREE_TEXT: "सेवा का ज़िक्र है, पर अस्पताल में होने की अलग से पुष्टि नहीं हुई।",
  NO_OFFICIAL_SOURCE: "अस्पताल का अपना कोई स्रोत नहीं मिला।",
};

/** What we could not confirm, in the page language (Hindi is built from the reason codes). */
export function unsureMessages(
  uncertainty: { messages: string[]; reasonCodes: string[] },
  lang: Lang,
): string[] {
  if (lang !== "hi") return uncertainty.messages;
  return [
    "मौजूदा उपलब्धता, समय, बिस्तर और खर्च की जानकारी डेटा में नहीं है।",
    ...uncertainty.reasonCodes.map((code) => UNSURE_HI[code]).filter(Boolean),
  ];
}

/** The one most specific thing we could not confirm, for the warning line on a card. */
export function cardWarning(uncertainty: { messages: string[]; reasonCodes: string[] }, lang: Lang): string | undefined {
  const all = unsureMessages(uncertainty, lang);
  const specific = lang === "hi" ? all.slice(1) : all.filter((m) => !/^Current availability/.test(m));
  return specific[0] ?? all[0];
}
