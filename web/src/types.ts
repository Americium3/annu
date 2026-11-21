export type RankingMode = "best_match" | "nearest" | "most_evidence";
export type ConfidenceLevel = "high" | "medium" | "low";
export type SourceType = "official_site" | "government" | "directory" | "social_media" | "unknown";
export type EvidenceStrength = "strong" | "medium" | "weak";
export type EvidencePolarity = "positive" | "negative" | "uncertain";

export interface ServiceOption {
  id: string;
  name: string;
  synonyms: string[];
  category: "dialysis" | "emergency" | "specialty" | "diagnostic";
}

export interface LocationOption {
  id: string;
  name: string;
  region: string;
  latitude: number;
  longitude: number;
  confidence: ConfidenceLevel;
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
    radiusKm: number;
    limit: number;
    rankingMode: RankingMode;
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
  latitude: number;
  longitude: number;
  distanceKm: number;
  totalScore: number;
  confidence: ConfidenceLevel;
  recommendationSummary: string;
  scoreBreakdown: ScoreBreakdown;
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
  };
}
