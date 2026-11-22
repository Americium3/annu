import { demoFacilities, locations, orderFacilities, services } from "../data/demo";
import type {
  FacilityRecommendation,
  LocationOption,
  RecommendationResponse,
  ServiceOption,
} from "../types";

const WAIT_TIME_MS = 520;
const DEMO_RADIUS_KM = 10;
const DEMO_LIMIT = 8;
const DEMO_TRAVEL_KM: Record<string, number> = {
  "kidney-dialysis": 15, "emergency-c-section": 10, nicu: 10, "burn-care": 10, mri: 30, "cardiac-surgery": 60,
};

interface DemoServiceProfile {
  fieldNames: [string, string, string];
  quotes: [string, string, string];
  summary: string;
  tags: [string, string];
}

const serviceProfiles: Record<string, DemoServiceProfile> = {
  "emergency-c-section": {
    fieldNames: ["emergency_services", "facility_capabilities", "registered_services"],
    quotes: [
      "The hospital lists an emergency obstetric theatre and 24-hour anaesthesia cover for emergency caesarean sections.",
      "Obstetric critical care, blood-bank support and emergency surgical capacity are included in the facility profile.",
      "Obstetrics and emergency surgery appear in the registered service list; current operating status is not stated.",
    ],
    summary:
      "Emergency obstetric theatre and anaesthesia cover are described, with supporting emergency surgery and blood-bank signals.",
    tags: ["Emergency obstetrics", "Anaesthesia cover"],
  },
  nicu: {
    fieldNames: ["neonatal_services", "equipment", "facility_capabilities"],
    quotes: [
      "The hospital lists a neonatal intensive care unit with respiratory support for premature and critically unwell newborns.",
      "Level III neonatal beds, neonatal ventilation and 24-hour paediatric cover are noted in the service profile.",
      "Neonatal special care appears in the service list; available cot capacity is not published.",
    ],
    summary:
      "A neonatal intensive care unit and respiratory-support capability are described, with paediatric coverage noted as a secondary signal.",
    tags: ["NICU listed", "Paediatric cover"],
  },
  "cardiac-surgery": {
    fieldNames: ["procedure_services", "critical_care", "department_list"],
    quotes: [
      "Cardiac operating theatres and cardiothoracic surgical support are listed for adult elective and urgent procedures.",
      "The facility profile notes a cardiac ICU, perfusion support and post-operative recovery capacity.",
      "Cardiology and cardiac surgery appear in the department list; the operating schedule is not stated.",
    ],
    summary:
      "Cardiothoracic operating capacity and cardiac critical-care support are described in the available facility sources.",
    tags: ["Cardiothoracic surgery", "Cardiac ICU"],
  },
  mri: {
    fieldNames: ["diagnostic_imaging", "equipment", "facility_capabilities"],
    quotes: [
      "The imaging department lists an MRI scanner and routine outpatient magnetic resonance imaging appointments.",
      "MRI equipment is named in the facility capability profile; scan strength and operating hours are not consistently stated.",
      "Diagnostic imaging appears in the service directory; current MRI availability requires confirmation.",
    ],
    summary:
      "MRI equipment and diagnostic imaging services are described, with equipment detail and operating-hours uncertainty surfaced.",
    tags: ["MRI scanner", "Diagnostic imaging"],
  },
  "burn-care": {
    fieldNames: ["specialty_services", "clinical_services", "registered_services"],
    quotes: [
      "The hospital lists a dedicated burn-treatment area and coordinated emergency surgery support.",
      "Burn dressings, fluid resuscitation and intensive-care transfer pathways are described in the clinical service profile.",
      "Burn care appears in the facility service list; dedicated bed capacity is not confirmed.",
    ],
    summary:
      "Dedicated burn-treatment and critical-care support signals are present, while bed capacity and current availability remain uncertain.",
    tags: ["Burn treatment", "Critical-care pathway"],
  },
};

function delay(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

export interface DemoSearchInput {
  serviceText: string;
  locationText: string;
  coordinates?: {
    latitude: number;
    longitude: number;
  };
}

export function resolveService(input: string): ServiceOption {
  const normalized = input.trim().toLowerCase();
  const matched =
    services.find(
      (service) =>
        service.name.toLowerCase() === normalized ||
        service.synonyms.some((synonym) => synonym.toLowerCase() === normalized),
    ) ??
    services.find(
      (service) =>
        service.name.toLowerCase().includes(normalized) ||
        service.synonyms.some((synonym) =>
          synonym.toLowerCase().includes(normalized),
        ),
    );

  return matched ?? services[0];
}

export function resolveLocation(input: string): LocationOption {
  const normalized = input.trim().toLowerCase();
  return (
    locations.find(
      (location) =>
        location.name.toLowerCase() === normalized ||
        `${location.name}, ${location.region}`.toLowerCase() === normalized ||
        normalized.includes(location.name.toLowerCase()),
    ) ?? locations[0]
  );
}

function adaptFacilityToService(
  facility: FacilityRecommendation,
  service: ServiceOption,
): FacilityRecommendation {
  const profile = serviceProfiles[service.id];
  if (!profile) return facility;

  const sourceIds = new Map(
    facility.sources.map((source) => [source.id, `${source.id}-${service.id}`]),
  );
  const sources = facility.sources.map((source) => ({
    ...source,
    id: sourceIds.get(source.id)!,
    url: `${source.url}?service=${service.id}`,
    title:
      source.sourceType === "official_site"
        ? `${service.name} — ${facility.name}`
        : source.sourceType === "government"
          ? `Odisha registered facilities directory`
          : source.sourceType === "directory"
            ? `${facility.name} profile`
            : `${facility.name} service update`,
    supportsClaims: source.supportsClaims.map(
      (evidenceId) => `${evidenceId}-${service.id}`,
    ),
  }));
  const evidence = facility.evidence.map((item, index) => {
    const lowConfidence = facility.confidence === "low";
    return {
      ...item,
      id: `${item.id}-${service.id}`,
      fieldName: profile.fieldNames[index] ?? profile.fieldNames[0],
      matchedService: service.name,
      quote: profile.quotes[index] ?? profile.quotes[2],
      matchType:
        index === 0 ? ("exact" as const) : index === 1 ? ("semantic" as const) : ("synonym" as const),
      polarity: lowConfidence && index > 0 ? ("uncertain" as const) : ("positive" as const),
      strength:
        facility.confidence === "high"
          ? ("strong" as const)
          : facility.confidence === "medium"
            ? ("medium" as const)
            : ("weak" as const),
      sourceId: sourceIds.get(item.sourceId)!,
    };
  });

  return {
    ...facility,
    recommendationSummary:
      facility.confidence === "low"
        ? `${profile.summary} Evidence is limited, so availability should be confirmed before travelling.`
        : profile.summary,
    evidence,
    sources,
    uncertainty: {
      level:
        facility.confidence === "high"
          ? "low"
          : facility.confidence === "medium"
            ? "medium"
            : "high",
      reasonCodes:
        facility.confidence === "high"
          ? []
          : facility.confidence === "medium"
            ? ["STALE_SOURCE"]
            : ["SERVICE_ONLY_IN_FREE_TEXT", "NO_OFFICIAL_SOURCE"],
      messages:
        facility.confidence === "high"
          ? [
              `Current ${service.name.toLowerCase()} availability and wait times are not published.`,
              "Confirm the service before travelling.",
            ]
          : facility.confidence === "medium"
            ? [
                `Some ${service.name.toLowerCase()} details come from older or secondary sources.`,
                "Call the facility to confirm current equipment and availability.",
              ]
            : [
                `${service.name} is mentioned, but on-site availability is not independently confirmed.`,
                "Contact the facility before relying on this result.",
              ],
      missingFields: ["current_availability", "capacity"],
      conflicts: [],
    },
    tags: [
      profile.tags[0],
      profile.tags[1],
      `${facility.distanceKm.toFixed(1)} km away`,
    ],
  };
}

export async function getDemoRecommendations(
  input: DemoSearchInput,
): Promise<RecommendationResponse> {
  await delay(WAIT_TIME_MS);

  const service = resolveService(input.serviceText);
  const location = resolveLocation(input.locationText);
  // Same rule as the live recommender: rank score = proof strength x closeness,
  // weak proof always after solid proof.
  const travel = DEMO_TRAVEL_KM[service.id] ?? 25;
  const sorted = orderFacilities(demoFacilities)
    .slice(0, DEMO_LIMIT)
    .map((facility) => adaptFacilityToService(facility, service))
    .map((facility) => {
      const tier = facility.confidence === "high" ? 1 : facility.confidence === "medium" ? 2 : 3;
      const proof = { 1: 1, 2: 0.8, 3: 0.55 }[tier]!;
      const closeness = 1 / (1 + (facility.distanceKm / travel) ** 2);
      const score = proof * closeness;
      return {
        ...facility,
        totalScore: Math.round(score * 100),
        rankFactors: {
          proof, closeness: Math.round(closeness * 100) / 100, score: Math.round(score * 100) / 100, travelKm: travel,
          proofTier: tier, onlyEquipment: false, mentionsOther: false, locationTier: "point_verified",
          statements: facility.evidence.length, solidProof: proof >= 0.5,
        },
      };
    })
    .sort((a, b) => Number(b.rankFactors.solidProof) - Number(a.rankFactors.solidProof) || b.rankFactors.score - a.rankFactors.score);
  const requestId = `demo-${Date.now().toString(36)}`;

  return {
    queryContext: {
      requestId,
      service: {
        canonicalId: service.id,
        displayName: service.name,
        matchedSynonyms: service.synonyms,
        confidence: "high",
      },
      location: {
        type: input.coordinates ? "coordinates" : "city",
        inputValue: input.locationText,
        resolvedName: location.name,
        district: location.name === "Bhubaneswar" ? "Khordha" : location.name,
        state: location.region,
        latitude: input.coordinates?.latitude ?? location.latitude,
        longitude: input.coordinates?.longitude ?? location.longitude,
        confidence: location.confidence,
      },
      searchParameters: {
        radiusKm: DEMO_RADIUS_KM,
        limit: DEMO_LIMIT,
      },
    },
    results: sorted.map((facility, index) => ({
      ...facility,
      rank: index + 1,
    })),
    metadata: {
      requestId,
      rankingVersion: "proof-x-closeness-v3 (demo)",
      generatedAt: new Date().toISOString(),
      totalCandidates: demoFacilities.length,
      returnedCount: sorted.length,
      isPartialResult: false,
      executionTimeMs: 438,
      warnings: [
        "Demo data only. Facility names and sources are illustrative.",
        service.id === "kidney-dialysis"
          ? "Dialysis evidence comes from the detailed hand-authored demo dataset."
          : `The ${service.name} scenario uses frontend-generated demo evidence and is not suitable for real care decisions.`,
      ],
    },
  };
}
