import { AlertTriangle, ArrowRight, HelpCircle, ShieldAlert } from "lucide-react";
import { operatorLabel, useI18n } from "../i18n";
import { transitionName } from "../lib/motion";
import { displayPhone, telUrl } from "../lib/facilityActions";
import { cardWarning, facilityType } from "../lib/localize";
import { verdictLabel, verdictWarns } from "../lib/verdict";
import { knownOperator, reasonText, statusLabel } from "../lib/reason";
import type { FacilityRecommendation } from "../types";
import { FacilityActions } from "./FacilityActions";

/** Pin colour by rank score (proof x closeness): 70+ strong, 45+ fair, else weak. */
export function scoreBand(score: number) {
  return score >= 70 ? "strong" : score >= 45 ? "mid" : "low";
}

type T = ReturnType<typeof useI18n>["t"];

/** One plain sentence on whether the service is confirmed, and by what. */
export function reasonLine(t: T, facility: FacilityRecommendation) {
  return reasonText(t, facility.confidence, facility.sources.map((source) => source.sourceType), facility);
}

/**
 * A warning only when one is needed. A confirmed result says nothing: being
 * listed already means it offers the service. Otherwise one short line names
 * what to do with what the card offers (call this number, check the website),
 * or says plainly that it isn't confirmed. The full reason is in the tooltip
 * and in "Why this hospital?".
 */
function Status({ facility, large = false }: { facility: FacilityRecommendation; large?: boolean }) {
  const { t } = useI18n();
  const { text, confirmed } = reasonLine(t, facility);
  const risky = facility.confidence === "low" || facility.uncertainty.level === "high";
  if (confirmed && !risky) return null; // nothing to warn about: say nothing
  const level = risky ? "low" : "medium";
  const Icon = level === "medium" ? HelpCircle : AlertTriangle;
  const label = statusLabel(t, level, facility);
  // "Call first" names the number and dials it, so the advice can be acted on.
  if (facility.phone) {
    return (
      <p className={`card-reason board-status ${large ? "is-large" : ""} confidence-${level}`} title={text}>
        <Icon size={15} aria-hidden="true" />
        <a href={telUrl(facility.phone)} onClick={(event) => event.stopPropagation()}>
          {label} · <span className="action-number">{displayPhone(facility.phone)}</span>
        </a>
        <span className="sr-only">: {text}</span>
      </p>
    );
  }
  return (
    <p className={`card-reason board-status ${large ? "is-large" : ""} confidence-${level}`} title={text}>
      <Icon size={15} aria-hidden="true" />
      {label}
      <span className="sr-only">: {text}</span>
    </p>
  );
}

/** "Type · Ownership · Area", leaving out ownership the data doesn't know. */
function Meta({ facility }: { facility: FacilityRecommendation }) {
  const { t, lang } = useI18n();
  const operator = knownOperator(facility.operatorType);
  return (
    <p className="facility-meta">
      {facilityType(facility.type, lang)} ·{" "}
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
  const { t, lang } = useI18n();
  // The language model's reading wins when it found a problem: it read this hospital's own record.
  if (facility.judgement && verdictWarns(facility.judgement.verdict)) {
    return (
      <p className="card-warning">
        <ShieldAlert size={16} aria-hidden="true" />
        {verdictLabel(t, facility.judgement.verdict)}
      </p>
    );
  }
  if (facility.uncertainty.level !== "high") return null;
  return (
    <p className="card-warning">
      <ShieldAlert size={16} aria-hidden="true" />
      {cardWarning(facility.uncertainty, lang)}
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
          <Status facility={facility} large />
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
        {facility.judgement && verdictWarns(facility.judgement.verdict) ? (
          <Warning facility={facility} />
        ) : (
          <Status facility={facility} />
        )}
      </div>
      <div className="board-actions">
        <FacilityActions facility={facility} service={service} compact />
        <WhyButton onOpen={onOpen} />
      </div>
    </li>
  );
}
