import {
  ArrowRight,
  Building2,
  Clock3,
  ExternalLink,
  MapPin,
  ShieldAlert,
} from "lucide-react";
import type { FacilityRecommendation } from "../types";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { ScoreRing } from "./ScoreRing";

interface FacilityCardProps {
  facility: FacilityRecommendation;
  selected: boolean;
  onSelect: () => void;
  onOpen: () => void;
}

export function FacilityCard({
  facility,
  selected,
  onSelect,
  onOpen,
}: FacilityCardProps) {
  const topEvidence = facility.evidence.slice(0, 2);
  const primarySource = facility.sources[0];

  return (
    <article
      className={`facility-card ${selected ? "is-selected" : ""}`}
      onClick={onSelect}
      aria-labelledby={`facility-${facility.id}-name`}
    >
      <div className="facility-rank" aria-label={`Rank ${facility.rank}`}>
        {facility.rank}
      </div>
      <div className="card-main">
        <div className="card-topline">
          <div>
            <div className="card-title-row">
              <h3 id={`facility-${facility.id}-name`}>{facility.name}</h3>
              <ConfidenceBadge level={facility.confidence} compact />
            </div>
            <p className="facility-meta">
              <Building2 size={14} aria-hidden="true" />
              {facility.type} <span>·</span> {facility.operatorType}
            </p>
          </div>
          <ScoreRing score={facility.totalScore} />
        </div>

        <div className="location-line">
          <MapPin size={14} aria-hidden="true" />
          <span>{facility.address}</span>
          <span className="middot">·</span>
          <strong>{facility.distanceKm.toFixed(1)} km</strong>
        </div>

        <p className="recommendation-summary">{facility.recommendationSummary}</p>

        <div className="evidence-preview">
          <div className="section-kicker">
            Why this facility
            <span>{topEvidence.length} strongest signals</span>
          </div>
          {topEvidence.map((evidence) => {
            const source = facility.sources.find((item) => item.id === evidence.sourceId);
            return (
              <div className="evidence-quote" key={evidence.id}>
                <p>“{evidence.quote}”</p>
                <span>
                  <code>{evidence.fieldName}</code>
                  <span className={`strength-strength-${evidence.strength}`}>
                    {evidence.strength} evidence
                  </span>
                </span>
              </div>
            );
          })}
        </div>

        <div className="card-footer">
          <div className="card-sources">
            {primarySource && (
              <a
                href={primarySource.url}
                target="_blank"
                rel="noreferrer"
                onClick={(event) => event.stopPropagation()}
              >
                <span className={`source-dot source-${primarySource.sourceType}`} />
                {primarySource.domain}
                <ExternalLink size={12} />
              </a>
            )}
            {facility.sources.length > 1 && (
              <span className="more-sources">+{facility.sources.length - 1} source</span>
            )}
          </div>
          <button
            className="text-button"
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpen();
            }}
          >
            See evidence
            <ArrowRight size={15} />
          </button>
        </div>

        {facility.uncertainty.level !== "low" && (
          <div className={`uncertainty-strip uncertainty-${facility.uncertainty.level}`}>
            {facility.uncertainty.level === "high" ? (
              <ShieldAlert size={15} aria-hidden="true" />
            ) : (
              <Clock3 size={15} aria-hidden="true" />
            )}
            <span>{facility.uncertainty.messages[0]}</span>
          </div>
        )}
      </div>
    </article>
  );
}
