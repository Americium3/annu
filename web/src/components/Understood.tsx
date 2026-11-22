import { ArrowRight, Crosshair, LoaderCircle, PencilLine, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { careName, careTerms } from "../data/careTerms";
import { useI18n } from "../i18n";
import { fetchLocations, fetchServices } from "../lib/api";
import { placeName } from "../lib/localize";
import type { AskResponse, AskSpan, LocationOption, ServiceOption } from "../types";
import { RaahiSays } from "./Raahi";

export type Coordinates = { latitude: number; longitude: number };

/** The person's sentence with the words each finding rests on marked, in reading order. */
export function SaidText({ answer }: { answer: AskResponse }) {
  const marks = [
    answer.urgency.span && answer.urgency.level < 4 ? { span: answer.urgency.span, kind: "urgent" } : null,
    answer.care?.span ? { span: answer.care.span, kind: "care" } : null,
    answer.careOptionsSpan ? { span: answer.careOptionsSpan, kind: "care" } : null,
    answer.place?.span ? { span: answer.place.span, kind: "place" } : null,
  ]
    .filter((m): m is { span: AskSpan; kind: string } => Boolean(m))
    .sort((a, b) => a.span.start - b.span.start);
  const parts: React.ReactNode[] = [];
  let at = 0;
  marks.forEach(({ span, kind }, index) => {
    if (span.start < at) return; // overlapping marks: keep the first
    parts.push(answer.text.slice(at, span.start));
    parts.push(
      <mark key={index} className={`said-mark said-mark--${kind}`} style={{ "--i": index } as React.CSSProperties}>
        {answer.text.slice(span.start, span.end)}
      </mark>,
    );
    at = span.end;
  });
  parts.push(answer.text.slice(at));
  return <p className="said-text">{parts}</p>;
}

/** 0-100 emergency score as a filling bar: calm green to amber to red. */
export function UrgencyMeter({ score, level, compact = false }: { score: number; level: number; compact?: boolean }) {
  const { t } = useI18n();
  const label = level <= 2 ? t.urgEmergency : level === 3 ? t.urgUrgent : t.urgNot;
  return (
    <div className={`urgency urgency--${level} ${compact ? "urgency--compact" : ""}`}>
      <div
        className="urgency-track"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={score}
        aria-label={t.emScore}
      >
        <i style={{ "--score": score / 100 } as React.CSSProperties} />
        <span className="urgency-threshold" aria-hidden="true" />
      </div>
      <span className="urgency-label">
        <strong>{score}</strong> {label}
      </span>
    </div>
  );
}

function CarePicker({ onPick }: { onPick: (id: string, name: string) => void }) {
  const { t, lang } = useI18n();
  const [query, setQuery] = useState("");
  const [services, setServices] = useState<ServiceOption[]>([]);
  useEffect(() => {
    fetchServices().then(setServices).catch(() => setServices([]));
  }, []);
  const options = useMemo(() => {
    const q = query.trim().toLowerCase();
    // The live catalogue when it loaded, else the lexicon (demo mode); names shown in the page language.
    const pool = services.length
      ? services.map((s) => ({ id: s.id, name: careName(s.id, lang, s.name), words: [s.name, ...s.synonyms] }))
      : careTerms.map((c) => ({ id: c.id, name: lang === "hi" ? c.hi : c.en, words: [c.en, ...c.say] }));
    return pool
      .filter((o) => !q || o.name.toLowerCase().includes(q) || o.words.some((w) => w.toLowerCase().includes(q)))
      .slice(0, 6);
  }, [lang, query, services]);
  return (
    <div className="picker">
      <input
        autoFocus
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={t.carePlaceholder}
        aria-label={t.careLabel}
      />
      <ul>
        {options.map((option) => (
          <li key={option.id}>
            <button type="button" onClick={() => onPick(option.id, option.name)}>
              {option.name}
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          </li>
        ))}
        {options.length === 0 && <li className="picker-empty">{t.noServiceMatch}</li>}
      </ul>
    </div>
  );
}

function PlacePicker({
  message,
  suggestions = [],
  onPick,
}: {
  message?: string;
  suggestions?: string[];
  onPick: (place: { text: string; coordinates?: Coordinates }) => void;
}) {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<LocationOption[]>([]);
  const [geo, setGeo] = useState<"idle" | "locating" | "error">("idle");
  useEffect(() => {
    const handle = window.setTimeout(() => {
      fetchLocations(query).then(setOptions).catch(() => setOptions([]));
    }, 160);
    return () => window.clearTimeout(handle);
  }, [query]);

  function locate() {
    if (!navigator.geolocation) return setGeo("error");
    setGeo("locating");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setGeo("idle");
        onPick({
          text: "",
          coordinates: { latitude: position.coords.latitude, longitude: position.coords.longitude },
        });
      },
      () => setGeo("error"),
      { enableHighAccuracy: true, timeout: 8000 },
    );
  }

  const names = [...new Set([...suggestions, ...options.map((o) => `${o.name}, ${o.region}`)])].slice(0, 5);
  return (
    <div className="picker">
      {message && <p className="picker-message">{message}</p>}
      <form
        className="picker-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (query.trim()) onPick({ text: query.trim() });
        }}
      >
        <input
          autoFocus
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t.placePlaceholder}
          aria-label={t.placeLabel}
        />
        <button type="button" className="picker-locate" onClick={locate} aria-label={t.useLocation} title={t.useLocation}>
          {geo === "locating" ? <LoaderCircle className="spin" size={18} /> : <Crosshair size={18} />}
        </button>
      </form>
      {geo === "error" && <p className="picker-message">{t.locationError}</p>}
      <ul>
        {names.map((name) => (
          <li key={name}>
            <button type="button" onClick={() => onPick({ text: name })}>
              {name}
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Raahi's reply: the person's words with what was found in them marked, one
 * row each for care, place and urgency (each with the exact words it came
 * from, and a way to change it), and a question when something is missing.
 */
export function Understood({
  answer,
  onPickCare,
  onPickPlace,
  topDistanceKm,
}: {
  answer: AskResponse;
  onPickCare: (id: string) => void;
  onPickPlace: (place: { text: string; coordinates?: Coordinates }) => void;
  topDistanceKm?: number;
}) {
  const { t, lang } = useI18n();
  const [editing, setEditing] = useState<"care" | "place" | null>(null);
  useEffect(() => setEditing(null), [answer]);

  const asking = answer.next === "ask_care" ? "care" : answer.next === "ask_place" ? "place" : null;
  const open = editing ?? asking;
  const care = answer.care;
  const place = answer.place;
  const travel = answer.results?.queryContext.searchParameters.travelKm;
  const urgentFar =
    answer.urgency.level === 3 && topDistanceKm !== undefined && travel !== undefined && topDistanceKm > 2 * travel;

  const placeLabel = place?.text
    ? placeName(place.text, lang)
    : place?.here || answer.results?.queryContext.location.type === "coordinates"
      ? t.currentLocation
      : null;
  const placeFrom =
    place?.span ? t.fromWords(place.span.quote) : place?.source === "saved" ? (place.here ? t.fromDevice : t.fromSaved) : null;

  return (
    <section className="understood" aria-live="polite" aria-labelledby="understood-title">
      <div className="said">
        <span className="said-label">{t.youSaid}</span>
        <SaidText answer={answer} />
      </div>

      <RaahiSays mood={answer.next === "results" ? "happy" : "thinking"} size={56} className="understood-raahi">
        <h2 id="understood-title" className="understood-title">
          {asking === "care"
            ? answer.careOptions.length
              ? t.askCareQ
              : t.askCareNone
            : asking === "place"
              ? t.askPlaceQ
              : t.understoodTitle}
        </h2>
      </RaahiSays>

      <dl className="understood-rows">
        <div className={`understood-row ${care ? "is-found" : "is-missing"}`} style={{ "--i": 0 } as React.CSSProperties}>
          <dt>{t.rowCare}</dt>
          <dd>
            {care ? (
              <>
                <strong>{careName(care.id, lang, care.name)}</strong>
                {care.span && <small>{t.fromWords(care.span.quote)}</small>}
              </>
            ) : (
              <span className="understood-missing">{answer.careOptions.length ? t.pickOne : t.notFound}</span>
            )}
          </dd>
          {care && (
            <button type="button" className="link-button" onClick={() => setEditing(open === "care" ? null : "care")}>
              <PencilLine size={15} aria-hidden="true" />
              {t.change}
            </button>
          )}
        </div>
        {open === "care" && (
          <div className="understood-ask">
            {answer.careOptions.length > 0 && !editing ? (
              <ul className="option-list">
                {answer.careOptions.map((option, index) => (
                  <li key={option.id} style={{ "--i": index } as React.CSSProperties}>
                    <button type="button" onClick={() => onPickCare(option.id)}>
                      <span>{lang === "hi" ? option.nameHi : option.name}</span>
                      <ArrowRight size={18} aria-hidden="true" />
                    </button>
                  </li>
                ))}
                <li>
                  <button type="button" className="option-other" onClick={() => setEditing("care")}>
                    {t.askCareOther}
                  </button>
                </li>
              </ul>
            ) : (
              <CarePicker onPick={(id) => onPickCare(id)} />
            )}
          </div>
        )}

        <div
          className={`understood-row ${placeLabel ? "is-found" : "is-missing"}`}
          style={{ "--i": 1 } as React.CSSProperties}
        >
          <dt>{t.rowPlace}</dt>
          <dd>
            {placeLabel ? (
              <>
                <strong>{placeLabel}</strong>
                {placeFrom && <small>{placeFrom}</small>}
              </>
            ) : (
              <span className="understood-missing">{t.notFound}</span>
            )}
          </dd>
          {placeLabel && (
            <button type="button" className="link-button" onClick={() => setEditing(open === "place" ? null : "place")}>
              <PencilLine size={15} aria-hidden="true" />
              {t.change}
            </button>
          )}
        </div>
        {open === "place" && (
          <div className="understood-ask">
            <PlacePicker
              message={answer.placeMessage ? localizePlaceMessage(answer.placeMessage, t) : undefined}
              suggestions={answer.placeSuggestions}
              onPick={onPickPlace}
            />
          </div>
        )}

        <div className="understood-row understood-row--urgency" style={{ "--i": 2 } as React.CSSProperties}>
          <dt>{t.rowUrgency}</dt>
          <dd>
            <UrgencyMeter score={answer.urgency.score} level={answer.urgency.level} />
            {answer.urgency.span && answer.urgency.level < 4 && <small>{t.fromWords(answer.urgency.span.quote)}</small>}
          </dd>
        </div>
      </dl>

      {urgentFar && (
        <p className="understood-warning">
          <TriangleAlert size={16} aria-hidden="true" />
          {t.urgentFar(topDistanceKm!.toFixed(0))}{" "}
          <a href="tel:108">{t.call108Short}</a>
        </p>
      )}
    </section>
  );
}

function localizePlaceMessage(message: string, t: ReturnType<typeof useI18n>["t"]) {
  if (/outside India/i.test(message)) return t.outsideIndia;
  if (/demo data only covers|No demo hospital/i.test(message)) return t.demoPlaceOnly;
  return t.placeNotFound;
}
