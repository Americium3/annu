import { ArrowRight, Crosshair, LoaderCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { careName, careTerms } from "../data/careTerms";
import { useI18n } from "../i18n";
import { fetchLocations, fetchServices } from "../lib/api";
import type { AskResponse, AskSpan, LocationOption, ServiceOption } from "../types";

export type Coordinates = { latitude: number; longitude: number };

/** The person's sentence with the words each finding rests on marked, in reading order. */
export function SaidText({ answer }: { answer: AskResponse }) {
  const marks = [
    answer.urgency.span && answer.urgency.level < 4 ? { span: answer.urgency.span, kind: "urgent" } : null,
    answer.care?.span ? { span: answer.care.span, kind: "care" } : null,
    answer.condition?.span ? { span: answer.condition.span, kind: "care" } : null,
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

export function CarePicker({ onPick }: { onPick: (id: string, name: string) => void }) {
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

export function PlacePicker({
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
