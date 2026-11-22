import { AlertTriangle, ArrowRight, CheckCircle2, HelpCircle, ShieldAlert } from "lucide-react";
import { operatorLabel, useI18n } from "../i18n";
import { transitionName } from "../lib/motion";
import type { FacilityRecommendation, SourceType } from "../types";
import { FacilityActions } from "./FacilityActions";

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

function Reason({ facility }: { facility: FacilityRecommendation }) {
  const { t } = useI18n();
  const Icon =
    facility.confidence === "high" ? CheckCircle2 : facility.confidence === "medium" ? HelpCircle : AlertTriangle;
  return (
    <p className={`card-reason confidence-${facility.confidence}`}>
      <Icon size={16} aria-hidden="true" />
      {reasonLine(t, facility)}
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
export function TopPick({ facility, service, selected, onSelect, onOpen, nearest = false }: ResultProps & { nearest?: boolean }) {
  const { t } = useI18n();
  return (
    <article
      className={`top-pick ${selected ? "is-selected" : ""}`}
      onClick={onSelect}
      aria-labelledby={`facility-${facility.id}-name`}
      style={{ "--vt-name": transitionName("result", facility.id) } as React.CSSProperties}
    >
      <p className="top-pick-label">{nearest ? t.topPickNearest : t.topPick}</p>
      <div className="top-pick-main">
        <Distance km={facility.distanceKm} large />
        <div className="top-pick-body">
          <h3 id={`facility-${facility.id}-name`}>{facility.name}</h3>
          <p className="facility-meta">
            {facility.type} · <span className="operator">{operatorLabel(t, facility.operatorType)}</span> ·{" "}
            {facility.address}
          </p>
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
        <p className="facility-meta">
          {facility.type} · <span className="operator">{operatorLabel(t, facility.operatorType)}</span> ·{" "}
          {facility.address}
        </p>
        <Reason facility={facility} />
        <Warning facility={facility} />
      </div>
      <div className="board-actions">
        <FacilityActions facility={facility} service={service} compact />
        <WhyButton onOpen={onOpen} />
      </div>
    </li>
  );
}
