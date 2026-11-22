import { AlertTriangle, ArrowRight, CheckCircle2, HelpCircle, ShieldAlert } from "lucide-react";
import { operatorLabel, useI18n } from "../i18n";
import type { FacilityRecommendation, SourceType } from "../types";
import { FacilityActions } from "./FacilityActions";

interface FacilityCardProps {
  facility: FacilityRecommendation;
  service: string;
  primary: boolean;
  selected: boolean;
  onSelect: () => void;
  onOpen: () => void;
}

export function scoreBand(score: number) {
  return score >= 85 ? "strong" : score >= 70 ? "mid" : "low";
}

type T = ReturnType<typeof useI18n>["t"];

/** One plain sentence on whether the service is confirmed, and by what. */
export function reasonLine(t: T, facility: FacilityRecommendation) {
  if (facility.confidence === "medium") return t.reasonMedium;
  if (facility.confidence === "low") return t.reasonLow;
  const names: Record<SourceType, string> = {
    official_site: t.srcListOfficial,
    government: t.srcListGovernment,
    directory: t.srcListDirectory,
    social_media: t.srcListSocial,
    unknown: t.srcListUnknown,
  };
  const kinds = [...new Set(facility.sources.map((source) => source.sourceType))]
    .slice(0, 2)
    .map((kind) => names[kind]);
  return t.reasonHigh(kinds.join(` ${t.and} `));
}

/**
 * A result answers one question: should I go here? Name, distance, where it
 * is, whether the service is confirmed, and the buttons to act. The proof
 * behind it lives one tap away in "Why this hospital?".
 */
export function FacilityCard({ facility, service, primary, selected, onSelect, onOpen }: FacilityCardProps) {
  const { t } = useI18n();
  const ReasonIcon =
    facility.confidence === "high" ? CheckCircle2 : facility.confidence === "medium" ? HelpCircle : AlertTriangle;

  return (
    <article
      className={`facility-card ${primary ? "is-primary" : ""} ${selected ? "is-selected" : ""}`}
      onClick={onSelect}
      aria-labelledby={`facility-${facility.id}-name`}
    >
      <div className="card-head">
        <span
          className={`rank-pin rank-pin-${scoreBand(facility.totalScore)}`}
          aria-label={t.rank(facility.rank)}
        >
          <span>{facility.rank}</span>
        </span>
        <div className="card-title">
          <h3 id={`facility-${facility.id}-name`}>{facility.name}</h3>
          <p className="facility-meta">
            {facility.type} · <span className="operator">{operatorLabel(t, facility.operatorType)}</span> ·{" "}
            {facility.address}
          </p>
        </div>
        <p className="card-distance">
          <strong>{facility.distanceKm.toFixed(1)}</strong> km
        </p>
      </div>

      <div className="card-body">
        <p className={`card-reason confidence-${facility.confidence}`}>
          <ReasonIcon size={16} aria-hidden="true" />
          {reasonLine(t, facility)}
        </p>

        {facility.uncertainty.level === "high" && (
          <p className="card-warning">
            <ShieldAlert size={16} aria-hidden="true" />
            {facility.uncertainty.messages[0]}
          </p>
        )}

        <div className="card-footer">
          <FacilityActions facility={facility} service={service} primary={primary} />
          <button
            className="text-button"
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpen();
            }}
          >
            {t.whyHospital}
            <ArrowRight size={16} />
          </button>
        </div>
      </div>
    </article>
  );
}
