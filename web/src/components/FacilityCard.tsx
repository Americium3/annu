import { AlertTriangle, ArrowRight, CheckCircle2, HelpCircle, ShieldAlert } from "lucide-react";
import { operatorLabel, useI18n } from "../i18n";
import { transitionName } from "../lib/motion";
import { knownOperator, reasonText } from "../lib/reason";
import type { FacilityRecommendation } from "../types";
import { FacilityActions } from "./FacilityActions";

export function scoreBand(score: number) {
  return score >= 85 ? "strong" : score >= 70 ? "mid" : "low";
}

type T = ReturnType<typeof useI18n>["t"];

/** One plain sentence on whether the service is confirmed, and by what. */
export function reasonLine(t: T, facility: FacilityRecommendation) {
  return reasonText(t, facility.confidence, facility.sources.map((source) => source.sourceType));
}

function Reason({ facility }: { facility: FacilityRecommendation }) {
  const { t } = useI18n();
  const { text, confirmed } = reasonLine(t, facility);
  // Only a named source earns the green check; anything else reads as "check first".
  const level = confirmed ? "high" : facility.confidence === "low" ? "low" : "medium";
  const Icon = level === "high" ? CheckCircle2 : level === "medium" ? HelpCircle : AlertTriangle;
  return (
    <p className={`card-reason confidence-${level}`}>
      <Icon size={16} aria-hidden="true" />
      {text}
    </p>
  );
}

/**
 * The other options get a one-word status instead of a sentence; the full
 * reason is in the tooltip and in "Why this hospital?".
 */
function Status({ facility }: { facility: FacilityRecommendation }) {
  const { t } = useI18n();
  const { text, confirmed } = reasonLine(t, facility);
  const risky = facility.confidence === "low" || facility.uncertainty.level === "high";
  const level = confirmed && !risky ? "high" : risky ? "low" : "medium";
  const Icon = level === "high" ? CheckCircle2 : level === "medium" ? HelpCircle : AlertTriangle;
  const label = level === "high" ? t.statusConfirmed : level === "medium" ? t.statusCheck : t.statusNot;
  return (
    <p className={`card-reason board-status confidence-${level}`} title={text}>
      <Icon size={15} aria-hidden="true" />
      {label}
      <span className="sr-only">: {text}</span>
    </p>
  );
}

/** "Type · Ownership · Area", leaving out ownership the data doesn't know. */
function Meta({ facility }: { facility: FacilityRecommendation }) {
  const { t } = useI18n();
  const operator = knownOperator(facility.operatorType);
  return (
    <p className="facility-meta">
      {facility.type} ·{" "}
      {operator && (
        <>
          <span className="operator">{operatorLabel(t, operator)}</span> ·{" "}
        </>
      )}
      {facility.address}
    </p>
  );
}

function Warning({ facility }: { facility: FacilityRecommendation }) {
  if (facility.uncertainty.level !== "high") return null;
  return (
    <p className="card-warning">
      <ShieldAlert size={16} aria-hidden="true" />
      {facility.uncertainty.messages[0]}
    </p>
  );
}

function Distance({ km, large = false }: { km: number; large?: boolean }) {
  const { t } = useI18n();
  const [whole, fraction] = km.toFixed(1).split(".");
  return (
    <p className={`board-distance ${large ? "is-large" : ""}`}>
      <strong>
        {whole}
        <span>.{fraction}</span>
      </strong>
      <small>{t.kmUnit}</small>
    </p>
  );
}

interface ResultProps {
  facility: FacilityRecommendation;
  service: string;
  selected: boolean;
  index: number;
  onSelect: () => void;
  onOpen: () => void;
}

function WhyButton({ onOpen }: { onOpen: () => void }) {
  const { t } = useI18n();
  return (
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
  );
}

/**
 * The answer, set large: the one place this person should most likely go,
 * with the distance as the headline number and one filled action.
 */
export function TopPick({ facility, service, selected, onSelect, onOpen }: ResultProps & { nearest?: boolean }) {
  const { t } = useI18n();
  return (
    <article
      className={`top-pick ${selected ? "is-selected" : ""}`}
      onClick={onSelect}
      aria-labelledby={`facility-${facility.id}-name`}
      style={{ "--vt-name": transitionName("result", facility.id) } as React.CSSProperties}
    >
      <div className="top-pick-main">
        <Distance km={facility.distanceKm} large />
        <div className="top-pick-body">
          <h3 id={`facility-${facility.id}-name`}>{facility.name}</h3>
          <Meta facility={facility} />
          <Reason facility={facility} />
          <Warning facility={facility} />
        </div>
      </div>
      <div className="top-pick-actions">
        <FacilityActions facility={facility} service={service} primary />
        <WhyButton onOpen={onOpen} />
      </div>
    </article>
  );
}

/** Every other option as a board row: distance first, then who, then what to do. */
export function BoardRow({ facility, service, selected, index, onSelect, onOpen }: ResultProps) {
  const { t } = useI18n();
  return (
    <li
      className={`board-row ${selected ? "is-selected" : ""}`}
      onClick={onSelect}
      aria-labelledby={`facility-${facility.id}-name`}
      style={
        { "--vt-name": transitionName("result", facility.id), "--i": index } as React.CSSProperties
      }
    >
      <span className={`board-rank rank-${scoreBand(facility.totalScore)}`} aria-label={t.rank(facility.rank)}>
        {facility.rank}
      </span>
      <Distance km={facility.distanceKm} />
      <div className="board-body">
        <h3 id={`facility-${facility.id}-name`}>{facility.name}</h3>
        <Meta facility={facility} />
        <Status facility={facility} />
      </div>
      <div className="board-actions">
        <FacilityActions facility={facility} service={service} compact />
        <WhyButton onOpen={onOpen} />
      </div>
    </li>
  );
}
