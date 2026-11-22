import { ArrowLeft, Check, Copy, ExternalLink, X } from "lucide-react";
import { useEffect, useState } from "react";
import { operatorLabel, useI18n } from "../i18n";
import { facilityType, unsureMessages } from "../lib/localize";
import { verdictLabel, verdictWarns } from "../lib/verdict";
import { knownOperator } from "../lib/reason";
import type { FacilityRecommendation, SourceType } from "../types";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { reasonLine } from "./FacilityCard";
import { FacilityActions } from "./FacilityActions";
import { Raahi } from "./Raahi";
import { ScoreRing } from "./ScoreRing";

interface FacilityDetailProps {
  facility?: FacilityRecommendation;
  service: string;
  onClose: () => void;
}



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
                {[t.rank(facility.rank), facilityType(facility.type, lang), knownOperator(facility.operatorType) && operatorLabel(t, facility.operatorType)]
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
            {/* One plain sentence from the page's own copy (both languages); the proof and the ranking follow below. */}
            <p>{reasonLine(t, facility).text}</p>
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
              {unsureMessages(facility.uncertainty, lang).map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          </section>
          )}

          {facility.judgement && <JudgeSection facility={facility} />}

          {facility.rankFactors && <RankExplanation facility={facility} />}

          <section className="detail-section" id="evidence">
            <div className="detail-section-heading">
              <h3>{t.proofTitle}</h3>
              <span className="evidence-count">{t.items(facility.evidence.length)}</span>
            </div>
            {t.proofOriginal && <p className="proof-original">{t.proofOriginal}</p>}
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
                    {/* Some records have no page date: show none rather than throw on an invalid date. */}
                    {formatDay(source.retrievedAt, lang) && (
                      <small>
                        {t.retrieved} {formatDay(source.retrievedAt, lang)}
                      </small>
                    )}
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

/**
 * WHY it ranks here, in the recommender's own terms: rank score = proof
 * strength x closeness, with each factor's reasons spelled out.
 */
function RankExplanation({ facility }: { facility: FacilityRecommendation }) {
  const { t } = useI18n();
  const f = facility.rankFactors!;
  const pct = (value: number) => Math.round(value * 100);
  const proofReasons = [
    f.proofTier === 1 ? t.proofTier1 : f.proofTier === 2 ? t.proofTier2 : t.proofTier3,
    f.onlyEquipment && t.proofEquipment,
    f.mentionsOther && t.proofOther,
    f.llmVerdict && t.proofJudged(verdictLabel(t, f.llmVerdict)),
    f.locationTier === "point_verified"
      ? t.proofLocVerified
      : f.locationTier === "pin_area"
        ? t.proofLocPin
        : t.proofLocUnverified,
  ].filter(Boolean) as string[];
  return (
    <section className="detail-section rank-explain" aria-labelledby="rank-title">
      <div className="detail-section-heading">
        <h3 id="rank-title">{t.rankTitle}</h3>
      </div>
      <p className="rank-lede">{t.rankLede(facility.rank)}</p>
      {f.textMatch != null && (
        <div className="rank-factor">
          <div className="score-row">
            <span>{t.textMatchLabel}</span>
            <div className="score-track">
              <i style={{ width: `${pct(f.textMatch)}%` }} />
            </div>
            <strong>{pct(f.textMatch)}</strong>
          </div>
          <ul className="rank-reasons">
            <li>{t.textMatchNote}</li>
          </ul>
        </div>
      )}
      <div className="rank-factor">
        <div className="score-row">
          <span>{t.proofLabel}</span>
          <div className="score-track">
            <i style={{ width: `${pct(f.proof)}%` }} />
          </div>
          <strong>{pct(f.proof)}</strong>
        </div>
        <ul className="rank-reasons">
          {proofReasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </div>
      <div className="rank-factor">
        <div className="score-row">
          <span>{t.closenessLabel}</span>
          <div className="score-track">
            <i style={{ width: `${pct(f.closeness)}%` }} />
          </div>
          <strong>{pct(f.closeness)}</strong>
        </div>
        <ul className="rank-reasons">
          <li>{t.closenessNote(facility.distanceKm.toFixed(1), f.travelKm ?? 25)}</li>
        </ul>
      </div>
      <p className="rank-formula">
        {t.rankFormula(pct(f.evidence ?? f.proof), pct(f.closeness), pct(f.score))}
      </p>
      {!f.solidProof && <p className="rank-weak">{t.rankWeak}</p>}
      <p className="score-disclaimer">{t.scoreDisclaimer}</p>
    </section>
  );
}

/** The language model's reading of this hospital's record for the care asked, with the line it rests on. */
function JudgeSection({ facility }: { facility: FacilityRecommendation }) {
  const { t } = useI18n();
  const j = facility.judgement!;
  const at = j.line.toLowerCase().indexOf(j.quote.toLowerCase());
  return (
    <section className={`detail-section judge ${verdictWarns(j.verdict) ? "judge--warn" : ""}`} aria-labelledby="judge-title">
      <div className="detail-section-heading">
        <h3 id="judge-title">{t.judgeTitle}</h3>
      </div>
      <p className="judge-verdict">
        <Raahi size={30} mood={verdictWarns(j.verdict) ? "concerned" : "happy"} />
        <strong>{verdictLabel(t, j.verdict)}</strong>
      </p>
      <blockquote className="judge-line">
        “
        {at >= 0 ? (
          <>
            {j.line.slice(0, at)}
            <mark>{j.line.slice(at, at + j.quote.length)}</mark>
            {j.line.slice(at + j.quote.length)}
          </>
        ) : (
          j.line
        )}
        ”<small>{t.judgeField(j.field)}</small>
      </blockquote>
      {j.reason && <p className="judge-reason">{j.reason}</p>}
      <p className="score-disclaimer">{t.judgeNote}</p>
    </section>
  );
}

/** "4 Sept 2025" in the page language, or null when the value is missing or not a date. */
function formatDay(value: string | null | undefined, lang: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short", year: "numeric" }).format(date);
}
