import { ArrowRight, Phone } from "lucide-react";
import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { prefersReducedMotion } from "../lib/motion";
import { RaahiSays } from "./Raahi";
import { UrgencyMeter } from "./Understood";

/** Types `text` out, then reports done; with reduced motion it is shown whole at once. */
function useTyped(text: string, startDelay = 400, speed = 55) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (prefersReducedMotion()) {
      setCount(text.length);
      return;
    }
    setCount(0);
    let i = 0;
    let timer = window.setTimeout(function tick() {
      i += 1;
      setCount(i);
      if (i < text.length) timer = window.setTimeout(tick, speed);
    }, startDelay);
    return () => window.clearTimeout(timer);
  }, [speed, startDelay, text]);
  return { typed: text.slice(0, count), done: count >= text.length };
}

/** A beat after `when` turns true. */
function useAfter(when: boolean, ms: number) {
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (!when) return setOn(false);
    const timer = window.setTimeout(() => setOn(true), prefersReducedMotion() ? 0 : ms);
    return () => window.clearTimeout(timer);
  }, [ms, when]);
  return on;
}

function marked(text: string, words: Array<[string, string]>) {
  // Highlight each word (first occurrence) once typing is done.
  const spans = words
    .map(([word, kind]) => ({ at: text.indexOf(word), word, kind }))
    .filter((s) => s.at >= 0)
    .sort((a, b) => a.at - b.at);
  const out: React.ReactNode[] = [];
  let at = 0;
  spans.forEach((s, i) => {
    out.push(text.slice(at, s.at));
    out.push(
      <mark key={i} className={`said-mark said-mark--${s.kind}`} style={{ "--i": i } as React.CSSProperties}>
        {s.word}
      </mark>,
    );
    at = s.at + s.word.length;
  });
  out.push(text.slice(at));
  return out;
}

/** Scene 1: a request typed in everyday words; the care and the place light up and drop into place. */
function SayItScene() {
  const { t, lang } = useI18n();
  const { typed, done } = useTyped(t.intro1Sample);
  const showCards = useAfter(done, 900);
  const careWord = lang === "hi" ? "डायलिसिस" : "dialysis";
  const placeWord = lang === "hi" ? "कटक" : "Cuttack";
  return (
    <div className="intro-stage intro-say">
      <div className="intro-box" aria-hidden="true">
        <span>
          {done
            ? marked(t.intro1Sample, [
                [careWord, "care"],
                [placeWord, "place"],
              ])
            : typed}
          {!done && <i className="intro-caret" />}
        </span>
      </div>
      <div className={`intro-cards ${showCards ? "is-on" : ""}`} aria-hidden="true">
        <div className="intro-card intro-card--care">
          <small>{t.rowCare}</small>
          <strong>{t.intro1Care}</strong>
        </div>
        <div className="intro-card intro-card--place">
          <small>{t.rowPlace}</small>
          <strong>{t.intro1Place}</strong>
        </div>
      </div>
    </div>
  );
}

/** Scene 2: danger words fill the emergency meter past the line, and 108 comes forward. */
function EmergencyScene() {
  const { t, lang } = useI18n();
  const { typed, done } = useTyped(t.intro2Sample, 300, 50);
  const fill = useAfter(done, 500);
  const call = useAfter(done, 1700);
  const danger = lang === "hi" ? "सीने में दर्द" : "chest pain";
  return (
    <div className="intro-stage intro-emergency">
      <div className="intro-box" aria-hidden="true">
        <span>
          {done ? marked(t.intro2Sample, [[danger, "urgent"]]) : typed}
          {!done && <i className="intro-caret" />}
        </span>
      </div>
      <div className="intro-meter" aria-hidden="true">
        <UrgencyMeter score={fill ? 85 : 0} level={fill ? 2 : 4} />
      </div>
      <span className={`intro-108 ${call ? "is-on" : ""}`} aria-hidden="true">
        <Phone size={20} />
        {t.emCall}
      </span>
    </div>
  );
}

/** Scene 3: rows start nearest-first, proof bars fill, and the rows settle into proof x closeness order. */
function ProofScene() {
  const { t } = useI18n();
  const rows = [
    { name: t.intro3Rows[2], km: 0.8, proof: 0.3 },
    { name: t.intro3Rows[0], km: 3.4, proof: 1 },
    { name: t.intro3Rows[1], km: 6.1, proof: 0.8 },
  ];
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    if (prefersReducedMotion()) return setPhase(2);
    const a = window.setTimeout(() => setPhase(1), 600);
    const b = window.setTimeout(() => setPhase(2), 2100);
    return () => {
      window.clearTimeout(a);
      window.clearTimeout(b);
    };
  }, []);
  // Settled order: Kalinga (solid proof, near), Mahanadi, then the weak-proof clinic.
  const settled = [2, 0, 1];
  return (
    <div className="intro-stage intro-proof" aria-hidden="true">
      <ol className="intro-rank" style={{ "--rows": rows.length } as React.CSSProperties}>
        {rows.map((row, index) => (
          <li
            key={row.name}
            className={row.proof < 0.5 && phase === 2 ? "is-weak" : ""}
            style={{ "--pos": phase === 2 ? settled[index] : index } as React.CSSProperties}
          >
            <span className="intro-rank-n">{(phase === 2 ? settled[index] : index) + 1}</span>
            <span className="intro-rank-name">{row.name}</span>
            <span className="intro-rank-bar">
              <i style={{ "--w": phase >= 1 ? row.proof : 0 } as React.CSSProperties} />
            </span>
            <span className="intro-rank-km">{row.km} km</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

const SCENES = [
  { title: "intro1Title", body: "intro1Body", Stage: SayItScene, mood: "happy" },
  { title: "intro2Title", body: "intro2Body", Stage: EmergencyScene, mood: "concerned" },
  { title: "intro3Title", body: "intro3Body", Stage: ProofScene, mood: "happy" },
] as const;

export const INTRO_COUNT = SCENES.length;

/**
 * How CarePath works, shown by Raahi doing it: three short scenes between the
 * language choice and the setup questions. Each can be skipped.
 */
export function IntroScene({ index, onNext, onSkip }: { index: number; onNext: () => void; onSkip: () => void }) {
  const { t } = useI18n();
  const scene = SCENES[index];
  const last = index === SCENES.length - 1;
  return (
    <div className="intro" key={index}>
      <RaahiSays size={64} mood={scene.mood}>
        <h1 tabIndex={-1}>{t[scene.title]}</h1>
      </RaahiSays>
      <scene.Stage />
      <p className="flow-hint intro-body">{t[scene.body]}</p>
      <div className="intro-dots" aria-hidden="true">
        {SCENES.map((s, i) => (
          <i key={s.title} className={i === index ? "is-on" : i < index ? "is-done" : ""} />
        ))}
      </div>
      <div className="flow-actions">
        <button type="button" className="primary-button flow-primary" onClick={onNext}>
          {last ? t.introStart : t.introNext}
          <ArrowRight size={18} aria-hidden="true" />
        </button>
      </div>
      {!last && (
        <button type="button" className="link-button flow-skip" onClick={onSkip}>
          {t.introSkip}
        </button>
      )}
    </div>
  );
}
