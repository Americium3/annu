import { ArrowLeft, Check, Copy, ExternalLink, X } from "lucide-react";
import { useEffect, useState } from "react";
import { operatorLabel, useI18n } from "../i18n";
import { knownOperator } from "../lib/reason";
import type { FacilityRecommendation, SourceType } from "../types";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { FacilityActions } from "./FacilityActions";
import { Raahi } from "./Raahi";
import { ScoreRing } from "./ScoreRing";

interface FacilityDetailProps {
  facility?: FacilityRecommendation;
  service: string;
  onClose: () => void;
}

type NumericScoreKey = Exclude<
  keyof FacilityRecommendation["scoreBreakdown"],
  "totalScore" | "modelVersion"
>;

const scoreMaximums: Array<[NumericScoreKey, number]> = [
  ["serviceMatchScore", 29],
  ["evidenceScore", 24],
  ["sourceScore", 15],
  ["distanceScore", 10],
  ["locationQualityScore", 9],
  ["capacityScore", 7],
];

export function FacilityDetail({ facility, service, onClose }: FacilityDetailProps) {
  const [copied, setCopied] = useState(false);
  // Play the closing animation before the drawer unmounts.
  const [closing, setClosing] = useState(false);
  const close = () => {
    if (closing) return;
    setClosing(true);
    window.setTimeout(() => {
      setClosing(false);
      onClose();
    }, 220);
  };
  const { t, lang } = useI18n();
  const scoreLabels: Record<NumericScoreKey, string> = {
    serviceMatchScore: t.scoreService,
    evidenceScore: t.scoreEvidence,
    sourceScore: t.scoreSource,
    distanceScore: t.scoreDistance,
    locationQualityScore: t.scoreLocation,
    capacityScore: t.scoreCapacity,
    penaltyScore: t.scorePenalty,
  };
  const sourceTypeLabels: Record<SourceType, string> = {
    official_site: t.sourceOfficial,
    government: t.sourceGovernment,
    directory: t.sourceDirectory,
    social_media: t.sourceSocial,
    unknown: t.sourceUnknown,
  };
  const polarityLabels = {
    positive: t.polarityPositive,
    uncertain: t.polarityUncertain,
    negative: t.polarityNegative,
  };
  const strengthLabels = { strong: t.strengthStrong, medium: t.strengthMedium, weak: t.strengthWeak };

  useEffect(() => {
    if (!facility) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") close();
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
          `“${evidence.quote}” (${currentFacility.sources.find((source) => source.id === evidence.sourceId)?.domain ?? "source unavailable"})`,
      ),
      `Uncertainty: ${currentFacility.uncertainty.messages.join(" ")}`,
    ].join("\n\n");
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  return (
    <div className={`detail-backdrop ${closing ? "is-closing" : ""}`} role="presentation" onClick={close}>
      <section
        className="detail-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="detail-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="drawer-topbar">
          <button className="back-button" type="button" onClick={close}>
            <ArrowLeft size={18} />
            {t.back}
          </button>
          <div className="drawer-actions">
            <button
              className="icon-button"
              type="button"
              onClick={copyExplanation}
              aria-label={copied ? t.copied : t.copy}
              title={copied ? t.copied : t.copy}
            >
              {copied ? <Check size={18} /> : <Copy size={18} />}
            </button>
            <button className="icon-button" type="button" onClick={close} aria-label={t.close}>
              <X size={20} />
            </button>
          </div>
        </div>

        <div className="drawer-scroll">
          <div className="detail-hero">
            <div>
              <p className="detail-kicker">
                {[t.rank(facility.rank), facility.type, knownOperator(facility.operatorType) && operatorLabel(t, facility.operatorType)]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              <h2 id="detail-title">{facility.name}</h2>
              <p className="detail-location">
                {facility.address}, {facility.district}, {facility.state} {facility.pincode}
              </p>
              <p className="detail-meta">
                <ConfidenceBadge level={facility.confidence} />
                <span>{t.kmAway(facility.distanceKm.toFixed(1))}</span>
              </p>
            </div>
            <ScoreRing score={facility.totalScore} size="large" />
          </div>

          <FacilityActions facility={facility} service={service} />

          <div className="detail-summary">
            <h3>{t.summary}</h3>
            <p>{facility.recommendationSummary}</p>
          </div>

          {facility.uncertainty.messages.length > 0 && (
          <section className="uncertainty-panel" aria-labelledby="unsure-title">
            <div className="uncertainty-heading">
              <Raahi size={44} mood="concerned" />
              <div>
                <h3 id="unsure-title">{t.unsureTitle}</h3>
                <p>{t.unsureHint}</p>
              </div>
            </div>
            <ul>
              {facility.uncertainty.messages.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          </section>
          )}

          <section className="detail-section">
            <div className="detail-section-heading">
              <h3>{t.scoreTitle}</h3>
            </div>
            <div className="score-breakdown">
              {(facility.reranking ? [
                ["serviceMatchScore", 100 * facility.reranking.weights.text],
                ["evidenceScore", 100 * facility.reranking.weights.evidence],
                ["distanceScore", 100 * facility.reranking.weights.distance],
              ] as Array<[NumericScoreKey, number]> : scoreMaximums).map(([key, maximum]) => {
                const value = facility.scoreBreakdown[key];
                return (
                  <div className="score-row" key={key}>
                    <span>{facility.reranking && key === "evidenceScore" ? t.scoreEligibility : scoreLabels[key]}</span>
                    <div className="score-track">
                      <i style={{ width: `${maximum > 0 ? Math.min(100, Math.max(0, (value / maximum) * 100)) : 0}%` }} />
                    </div>
                    <strong>
                      {Number(value.toFixed(1))}
                      <small>/{maximum}</small>
                    </strong>
                  </div>
                );
              })}
              {facility.scoreBreakdown.penaltyScore !== 0 && (
                <div className="score-row score-penalty">
                  <span>{scoreLabels.penaltyScore}</span>
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
            <p className="score-disclaimer">{t.scoreDisclaimer}</p>
          </section>

          <section className="detail-section" id="evidence">
            <div className="detail-section-heading">
              <h3>{t.proofTitle}</h3>
              <span className="evidence-count">{t.items(facility.evidence.length)}</span>
            </div>
            <div className="full-evidence-list">
              {facility.evidence.map((evidence) => {
                const source = facility.sources.find(
                  (item) => item.id === evidence.sourceId,
                );
                return (
                  <article className={`full-evidence evidence-${evidence.polarity}`} key={evidence.id}>
                    <blockquote>“{evidence.quote}”</blockquote>
                    <p className="evidence-header">
                      <span className={`polarity polarity-${evidence.polarity}`}>
                        {polarityLabels[evidence.polarity]}
                      </span>
                      <span className={`strength strength-${evidence.strength}`}>
                        {strengthLabels[evidence.strength]}
                      </span>
                    </p>
                    <div className="evidence-source">
                      <span className={`source-dot source-${source?.sourceType ?? "unknown"}`} />
                      <span>{source?.title ?? t.sourceUnknown}</span>
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
              <h3>{t.sourcesTitle}</h3>
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
                  <span className={`source-dot source-${source.sourceType}`} />
                  <span className="source-card-copy">
                    <strong>{source.title}</strong>
                    <span>
                      {sourceTypeLabels[source.sourceType]} · {source.domain}
                    </span>
                    <small>
                      {t.retrieved}{" "}
                      {new Intl.DateTimeFormat(lang === "hi" ? "hi-IN" : "en-IN", {
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

          <p className="detail-footer-note">{t.detailFootnote}</p>
        </div>
      </section>
    </div>
  );
}
