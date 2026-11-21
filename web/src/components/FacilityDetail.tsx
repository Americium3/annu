import {
  ArrowLeft,
  Check,
  Copy,
  ExternalLink,
  Info,
  MapPin,
  ShieldAlert,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { FacilityRecommendation, SourceType } from "../types";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { ScoreRing } from "./ScoreRing";

interface FacilityDetailProps {
  facility?: FacilityRecommendation;
  onClose: () => void;
}

type NumericScoreKey = Exclude<
  keyof FacilityRecommendation["scoreBreakdown"],
  "totalScore" | "modelVersion"
>;

const scoreLabels: Array<[NumericScoreKey, string, number]> = [
  ["serviceMatchScore", "Service match", 29],
  ["evidenceScore", "Evidence quality", 24],
  ["sourceScore", "Source quality", 15],
  ["distanceScore", "Distance", 10],
  ["locationQualityScore", "Location quality", 9],
  ["capacityScore", "Capacity signals", 7],
];

const sourceTypeLabels: Record<SourceType, string> = {
  official_site: "Official",
  government: "Government",
  directory: "Directory",
  social_media: "Social",
  unknown: "Unknown",
};

export function FacilityDetail({ facility, onClose }: FacilityDetailProps) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!facility) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.body.classList.add("detail-open");
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.classList.remove("detail-open");
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [facility, onClose]);

  if (!facility) return null;
  const currentFacility = facility;

  async function copyExplanation() {
    const text = [
      `${currentFacility.name} — recommendation score ${currentFacility.totalScore}/100`,
      currentFacility.recommendationSummary,
      ...currentFacility.evidence.map(
        (evidence) =>
          `${evidence.fieldName}: “${evidence.quote}” (${currentFacility.sources.find((source) => source.id === evidence.sourceId)?.domain ?? "source unavailable"})`,
      ),
      `Uncertainty: ${currentFacility.uncertainty.messages.join(" ")}`,
    ].join("\n\n");
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  return (
    <div className="detail-backdrop" role="presentation" onClick={onClose}>
      <section
        className="detail-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="detail-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="drawer-topbar">
          <button className="back-button" type="button" onClick={onClose}>
            <ArrowLeft size={18} />
            Back to results
          </button>
          <div className="drawer-actions">
            <button className="icon-button" type="button" onClick={copyExplanation}>
              {copied ? <Check size={18} /> : <Copy size={18} />}
              <span className="sr-only">{copied ? "Copied" : "Copy explanation"}</span>
            </button>
            <button className="icon-button" type="button" onClick={onClose} aria-label="Close details">
              <X size={20} />
            </button>
          </div>
        </div>

        <div className="drawer-scroll">
          <div className="detail-hero">
            <div>
              <span className="detail-eyebrow">
                Rank #{facility.rank} · {facility.type}
              </span>
              <h2 id="detail-title">{facility.name}</h2>
              <p className="detail-location">
                <MapPin size={15} />
                {facility.address}, {facility.district}, {facility.state} {facility.pincode}
              </p>
              <div className="detail-badges">
                <ConfidenceBadge level={facility.confidence} />
                <span className="plain-badge">{facility.distanceKm.toFixed(1)} km away</span>
                <span className="plain-badge">{facility.operatorType}</span>
              </div>
            </div>
            <ScoreRing score={facility.totalScore} size="large" />
          </div>

          <div className="detail-summary">
            <span className="summary-icon">
              <Info size={18} />
            </span>
            <div>
              <strong>Recommendation summary</strong>
              <p>{facility.recommendationSummary}</p>
            </div>
          </div>

          <section className="detail-section">
            <div className="detail-section-heading">
              <div>
                <span className="section-number">01</span>
                <h3>Score breakdown</h3>
              </div>
              <span className="model-label">{facility.scoreBreakdown.modelVersion}</span>
            </div>
            <div className="score-breakdown">
              {scoreLabels.map(([key, label, maximum]) => {
                const value = facility.scoreBreakdown[key];
                return (
                  <div className="score-row" key={key}>
                    <span>{label}</span>
                    <div className="score-track">
                      <i style={{ width: `${Math.max(0, (value / maximum) * 100)}%` }} />
                    </div>
                    <strong>{value}</strong>
                  </div>
                );
              })}
              {facility.scoreBreakdown.penaltyScore !== 0 && (
                <div className="score-row score-penalty">
                  <span>Evidence penalty</span>
                  <div className="score-track">
                    <i
                      style={{
                        width: `${Math.min(100, Math.abs(facility.scoreBreakdown.penaltyScore) * 8)}%`,
                      }}
                    />
                  </div>
                  <strong>{facility.scoreBreakdown.penaltyScore}</strong>
                </div>
              )}
            </div>
            <p className="score-disclaimer">
              The score summarises the same signals the ranking uses; the order itself follows
              evidence-first rules (evidence tier, then distance band, then location quality). Scores do
              not measure clinical quality, safety, or health outcomes.
            </p>
          </section>

          <section className="detail-section" id="evidence">
            <div className="detail-section-heading">
              <div>
                <span className="section-number">02</span>
                <h3>Evidence behind this match</h3>
              </div>
              <span className="evidence-count">{facility.evidence.length} items</span>
            </div>
            <div className="full-evidence-list">
              {facility.evidence.map((evidence) => {
                const source = facility.sources.find(
                  (item) => item.id === evidence.sourceId,
                );
                return (
                  <article className={`full-evidence evidence-${evidence.polarity}`} key={evidence.id}>
                    <div className="evidence-header">
                      <code>{evidence.fieldName}</code>
                      <div>
                        <span className={`polarity-badge polarity-${evidence.polarity}`}>
                          {evidence.polarity}
                        </span>
                        <span className={`strength-badge strength-${evidence.strength}`}>
                          {evidence.strength}
                        </span>
                      </div>
                    </div>
                    <blockquote>“{evidence.quote}”</blockquote>
                    <div className="evidence-source">
                      <span className={`source-dot source-${source?.sourceType ?? "unknown"}`} />
                      <span>{source?.title ?? "Source unavailable"}</span>
                      {source && (
                        <a href={source.url} target="_blank" rel="noreferrer">
                          {source.domain}
                          <ExternalLink size={12} />
                        </a>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="detail-section">
            <div className="detail-section-heading">
              <div>
                <span className="section-number">03</span>
                <h3>Source references</h3>
              </div>
            </div>
            <div className="source-list">
              {facility.sources.map((source) => (
                <a
                  className="source-card"
                  key={source.id}
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span className={`source-icon source-icon-${source.sourceType}`}>
                    <ExternalLink size={16} />
                  </span>
                  <span className="source-card-copy">
                    <strong>{source.title}</strong>
                    <span>
                      {sourceTypeLabels[source.sourceType]} · {source.domain}
                    </span>
                    <small>
                      Retrieved{" "}
                      {new Intl.DateTimeFormat("en-IN", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                      }).format(new Date(source.retrievedAt))}
                    </small>
                  </span>
                  <ExternalLink className="source-arrow" size={16} />
                </a>
              ))}
            </div>
          </section>

          <section className="uncertainty-panel">
            <div className="uncertainty-heading">
              <ShieldAlert size={19} />
              <div>
                <strong>What may be missing or uncertain</strong>
                <span>Read before choosing or travelling</span>
              </div>
              <ConfidenceBadge level={facility.uncertainty.level} compact />
            </div>
            <ul>
              {facility.uncertainty.messages.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
            {facility.uncertainty.missingFields.length > 0 && (
              <div className="missing-fields">
                Missing signals:
                {facility.uncertainty.missingFields.map((field) => (
                  <code key={field}>{field}</code>
                ))}
              </div>
            )}
          </section>

          <div className="detail-footer-note">
            <Info size={15} />
            CarePath helps compare publicly available evidence. It does not provide medical advice
            or guarantee treatment availability. Contact the facility before travelling.
          </div>
        </div>
      </section>
    </div>
  );
}
