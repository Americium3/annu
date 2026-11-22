import { MapPin, Stethoscope, Gauge } from "lucide-react";
import { careName } from "../data/careTerms";
import { useI18n } from "../i18n";
import { placeName } from "../lib/localize";
import type { AskResponse } from "../types";
import { UrgencyMeter } from "./Understood";

/**
 * What Raahi understood, as signposts planted along the trail: the care, the
 * place, and how urgent it is, each with the words it came from. The same
 * signs (same view-transition names) sit in the results page's summary bar,
 * so they glide there when the page changes. Only one set may carry the
 * names at a time (`shared`).
 */
export function Signposts({
  answer,
  shared = false,
  compact = false,
  onChange,
}: {
  answer: AskResponse;
  shared?: boolean;
  compact?: boolean;
  onChange?: (which: "care" | "place") => void;
}) {
  const { t, lang } = useI18n();
  const place = answer.place?.text
    ? placeName(answer.place.text, lang)
    : answer.place?.here || answer.results?.queryContext.location.type === "coordinates"
      ? t.currentLocation
      : null;
  const name = (n: string) => (shared ? ({ viewTransitionName: n } as React.CSSProperties) : undefined);
  const signs: Array<{ key: string; node: React.ReactNode }> = [];
  if (answer.care) {
    signs.push({
      key: "care",
      node: (
        <div className="sign sign--care" style={{ ...name("sign-care"), "--i": 0 } as React.CSSProperties}>
          <Stethoscope size={compact ? 15 : 17} aria-hidden="true" />
          <span className="sign-label">{t.rowCare}</span>
          <strong>{careName(answer.care.id, lang, answer.care.name)}</strong>
          {!compact && answer.care.span && <small>{t.fromWords(answer.care.span.quote)}</small>}
          {onChange && (
            <button type="button" className="sign-change" onClick={() => onChange("care")}>
              {t.change}
            </button>
          )}
        </div>
      ),
    });
  }
  if (place) {
    signs.push({
      key: "place",
      node: (
        <div className="sign sign--place" style={{ ...name("sign-place"), "--i": 1 } as React.CSSProperties}>
          <MapPin size={compact ? 15 : 17} aria-hidden="true" />
          <span className="sign-label">{t.rowPlace}</span>
          <strong>{place}</strong>
          {!compact && answer.place?.span && <small>{t.fromWords(answer.place.span.quote)}</small>}
          {!compact && answer.place?.source === "saved" && <small>{t.fromSaved}</small>}
          {onChange && (
            <button type="button" className="sign-change" onClick={() => onChange("place")}>
              {t.change}
            </button>
          )}
        </div>
      ),
    });
  }
  signs.push({
    key: "urgency",
    node: (
      <div
        className={`sign sign--urgency sign--u${answer.urgency.level}`}
        style={{ ...name("sign-urgency"), "--i": 2 } as React.CSSProperties}
      >
        <Gauge size={compact ? 15 : 17} aria-hidden="true" />
        <span className="sign-label">{t.rowUrgency}</span>
        <UrgencyMeter score={answer.urgency.score} level={answer.urgency.level} compact />
        {!compact && answer.urgency.span && answer.urgency.level < 4 && (
          <small>{t.fromWords(answer.urgency.span.quote)}</small>
        )}
      </div>
    ),
  });
  return (
    <div className={`signposts ${compact ? "signposts--compact" : ""}`}>
      {signs.map((s) => (
        <div key={s.key} className="signpost">
          {s.node}
        </div>
      ))}
    </div>
  );
}
