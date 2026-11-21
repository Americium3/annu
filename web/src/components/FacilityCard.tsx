import { ArrowRight, Clock3, ShieldAlert } from "lucide-react";
import { operatorLabel, useI18n } from "../i18n";
import type { FacilityRecommendation } from "../types";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { FacilityActions } from "./FacilityActions";
import { ScoreRing } from "./ScoreRing";

interface FacilityCardProps {
  facility: FacilityRecommendation;
  service: string;
  selected: boolean;
  onSelect: () => void;
  onOpen: () => void;
}

export function scoreBand(score: number) {
  return score >= 85 ? "strong" : score >= 70 ? "mid" : "low";
}

export function FacilityCard({ facility, service, selected, onSelect, onOpen }: FacilityCardProps) {
  const { t } = useI18n();
  const topEvidence = facility.evidence.slice(0, 2);
  const primarySource = facility.sources[0];
  const strengthLabel = {
    strong: t.strengthStrong,
    medium: t.strengthMedium,
    weak: t.strengthWeak,
  };

  return (
    <article
      className={`facility-card ${selected ? "is-selected" : ""}`}
      onClick={onSelect}
      aria-labelledby={`facility-${facility.id}-name`}
    >
      <header className="card-head">
        {/* Same pin as on the map, so list and map read as one thing. */}
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
            <strong>{t.kmAway(facility.distanceKm.toFixed(1))}</strong>
          </p>
          <p className="facility-address">{facility.address}</p>
        </div>
        <ScoreRing score={facility.totalScore} />
      </header>

      <div className="card-body">
        <div className="card-summary">
          <ConfidenceBadge level={facility.confidence} />
          <p>{facility.recommendationSummary}</p>
        </div>

        <h4 className="card-subhead">{t.whyListed}</h4>
        <ul className="quote-list">
          {topEvidence.map((evidence) => (
            <li key={evidence.id}>
              <blockquote>“{evidence.quote}”</blockquote>
              <p className="quote-meta">
                <span className={`strength strength-${evidence.strength}`}>
                  {strengthLabel[evidence.strength]}
                </span>
                <code>{evidence.fieldName}</code>
              </p>
            </li>
          ))}
        </ul>

        {primarySource && (
          <p className="card-source">
            {t.source}:{" "}
            <a
              href={primarySource.url}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => event.stopPropagation()}
            >
              {primarySource.domain}
            </a>
            {facility.sources.length > 1 && <> {t.andMore(facility.sources.length - 1)}</>}
          </p>
        )}

        <div className="card-footer">
          <FacilityActions facility={facility} service={service} />
          <button
            className="text-button"
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpen();
            }}
          >
            {t.seeProof}
            <ArrowRight size={16} />
          </button>
        </div>
      </div>

      {facility.uncertainty.level !== "low" && (
        <p className={`uncertainty-strip uncertainty-${facility.uncertainty.level}`}>
          {facility.uncertainty.level === "high" ? (
            <ShieldAlert size={16} aria-hidden="true" />
          ) : (
            <Clock3 size={16} aria-hidden="true" />
          )}
          <span>{facility.uncertainty.messages[0]}</span>
        </p>
      )}
    </article>
  );
}
