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
  /** Front-desk number in E.164 or local form. Absent when no source lists one. */
  phone?: string;
  /** The facility's own website, when the data has one. */
  website?: string;
  latitude: number;
  longitude: number;
  distanceKm: number;
  totalScore: number;
  confidence: ConfidenceLevel;
  recommendationSummary: string;
  scoreBreakdown: ScoreBreakdown;
  reranking?: {
    method: "cross_encoder";
    model: string;
    textScore: number;
    evidenceScore: number;
    distanceScore: number;
    totalScore: number;
    weights: { text: number; evidence: number; distance: number };
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
