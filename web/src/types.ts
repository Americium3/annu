export type ConfidenceLevel = "high" | "medium" | "low";
export type SourceType = "official_site" | "government" | "directory" | "social_media" | "unknown";
export type EvidenceStrength = "strong" | "medium" | "weak";
export type EvidencePolarity = "positive" | "negative" | "uncertain";

export interface ServiceOption {
  id: string;
  name: string;
  synonyms: string[];
  category: string;
  facilityCount?: number;
}

export interface LocationOption {
  id: string;
  name: string;
  region: string;
  latitude: number;
  longitude: number;
  confidence: ConfidenceLevel;
  kind?: "district" | "city" | "pincode";
}

export interface QueryContext {
  requestId: string;
  service: {
    canonicalId: string;
    displayName: string;
    matchedSynonyms: string[];
    confidence: ConfidenceLevel;
  };
  location: {
    type: "city" | "district" | "pincode" | "coordinates";
    inputValue: string;
    resolvedName: string;
    district: string;
    state: string;
    latitude: number;
    longitude: number;
    confidence: ConfidenceLevel;
  };
  searchParameters: {
    /** Chosen by the system (search widens until a provider is found), not by the user. */
    radiusKm: number;
    limit: number;
    /** Distance at which closeness halves; halved again when the request is urgent. */
    travelKm?: number;
    /** From the person's words: 3 = needs care today, 4 = not urgent. */
    urgencyLevel?: number;
  };
}

export interface EvidenceItem {
  id: string;
  fieldName: string;
  matchedService: string;
  quote: string;
  matchType: "exact" | "synonym" | "semantic";
  polarity: EvidencePolarity;
  strength: EvidenceStrength;
  sourceId: string;
}

export interface SourceReference {
  id: string;
  url: string;
  domain: string;
  sourceType: SourceType;
  title: string;
  retrievedAt: string;
  supportsClaims: string[];
}

export interface ScoreBreakdown {
  serviceMatchScore: number;
  evidenceScore: number;
  sourceScore: number;
  distanceScore: number;
  locationQualityScore: number;
  capacityScore: number;
  penaltyScore: number;
  totalScore: number;
  modelVersion: string;
}

export interface Uncertainty {
  level: ConfidenceLevel;
  reasonCodes: string[];
  messages: string[];
  missingFields: string[];
  conflicts: string[];
}

export interface RankFactors {
  /** 0-1: how strongly the evidence says it offers the service, at a location we trust. */
  proof: number;
  /** 0-1: 1 next door, 0.5 at travelKm. */
  closeness: number;
  /** proof x closeness: the number the list is sorted by. */
  score: number;
  /** How far people reasonably travel for this kind of care (km). */
  travelKm: number | null;
  proofTier: number;
  onlyEquipment: boolean;
  mentionsOther: boolean;
  locationTier: string;
  statements: number;
  /** False: weak proof, always listed after every facility with solid proof. */
  solidProof: boolean;
  /** 0-1 cross-encoder match between the best quote and the service; null in rules mode. */
  textMatch?: number | null;
  /** 0-1 evidence strength: proof alone, or blended with text match. */
  evidence?: number;
  /** The language model's verdict on this hospital's own record lines, when it judged them. */
  llmVerdict?: JudgeVerdict | null;
}

export type JudgeVerdict = "offers" | "likely" | "mentions_only" | "equipment_only" | "not_supported";

/** A language model read this hospital's record lines for the care asked (backend/judge.py). */
export interface Judgement {
  verdict: JudgeVerdict;
  /** Record field the deciding line came from: procedure, capability, equipment, specialty, description. */
  field: string;
  /** The model's quote, found verbatim in `line`. */
  quote: string;
  line: string;
  reason: string;
  model: string | null;
}

export interface FacilityRecommendation {
  id: string;
  rank: number;
  name: string;
  type: string;
  operatorType: string;
  address: string;
  district: string;
  state: string;
  pincode: string;
  /** Front-desk number in E.164 or local form. Absent when no source lists one. */
  phone?: string;
  /** The facility's own website, when the data has one. */
  website?: string;
  /** Why it ranks where it does: rank score = evidence strength x closeness. */
  rankFactors?: RankFactors;
  latitude: number;
  longitude: number;
  distanceKm: number;
  totalScore: number;
  confidence: ConfidenceLevel;
  recommendationSummary: string;
  scoreBreakdown: ScoreBreakdown;
  judgement?: Judgement;
  reranking?: {
    method: "cross_encoder";
    model: string;
    textScore: number;
    evidenceScore: number;
    distanceScore: number;
    totalScore: number;
    /** Shares of evidence strength: evidence = text x textMatch + proof x proofStrength. */
    weights: { text: number; proof: number };
    bestEvidenceRef: string;
    bestEvidenceText: string;
    scoredItemCount: number;
    scoreMeaning: string;
  };
  evidence: EvidenceItem[];
  sources: SourceReference[];
  locationQuality: {
    label: string;
    note: string;
  };
  dataCompleteness: number;
  uncertainty: Uncertainty;
  tags: string[];
}

export interface RecommendationResponse {
  queryContext: QueryContext;
  results: FacilityRecommendation[];
  metadata: {
    requestId: string;
    rankingVersion: string;
    generatedAt: string;
    totalCandidates: number;
    returnedCount: number;
    isPartialResult: boolean;
    executionTimeMs: number;
    warnings: string[];
    /** Whether the language model judged the top hospitals' records for this response. */
    judge?: { used: boolean; available: boolean; model?: string; asked?: number; judged?: number; error?: string };
    funnel?: {
      datasetProviders: number;
      datasetRecommendable: number;
      withinRadius: number;
      reviewBlockedWithinRadius: number;
      radiusStepsKm: number[];
      radiusKm: number;
      locationNote: string;
      serviceMatch: string;
      dataSource: string;
    };
  };
}

/** Where a finding comes from in the person's own words: text.slice(start, end) === quote. */
export interface AskSpan {
  quote: string;
  start: number;
  end: number;
}

export interface CareRef {
  id: string;
  name: string;
  nameHi: string;
}

/** /api/ask: what the person asked for, in their own words, and what to do next. */
export interface AskResponse {
  text: string;
  /** "rules+llm" when a Databricks-hosted model filled gaps (only grounded answers kept). */
  method: "rules" | "rules+llm";
  llm: { used: boolean; endpoint?: string | null; error?: string; kept?: string[]; dropped?: string[] };
  urgency: {
    level: 1 | 2 | 3 | 4;
    /** 0-100: 100 life-threatening, 85 emergency, 60 urgent, 15 not urgent. 80+ opens the emergency screen. */
    score: number;
    label: string;
    rule: string | null;
    source: "rules" | "llm" | "none";
    crisis: boolean;
    emergency: boolean;
    span?: AskSpan;
  };
  care: (CareRef & { source: string; span?: AskSpan }) | null;
  /** What the person described (a symptom, or a disease they named), never a guessed cause. */
  condition?: { name: string; nameHi?: string | null; source: string; span?: AskSpan } | null;
  /** A broad word ("kidney") fits several kinds of care: the person picks one. */
  careOptions: CareRef[];
  careOptionsSpan?: AskSpan;
  place: { text: string | null; here: boolean; source: string; span?: AskSpan } | null;
  next: "emergency" | "ask_care" | "ask_place" | "results";
  results?: RecommendationResponse;
  placeMessage?: string;
  placeSuggestions?: string[];
  careMessage?: string;
}
