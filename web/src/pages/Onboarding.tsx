import { ArrowRight, Check, Crosshair, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Header } from "../components/Header";
import { IntroScene } from "../components/IntroScenes";
import { RaahiSays } from "../components/Raahi";
import { locations } from "../data/demo";
import { useI18n, type Lang } from "../i18n";
import { useSession } from "../lib/auth";
import { formatPhone } from "../lib/auth";
import { withTransition } from "../lib/motion";
import { isValidMobile, profileSnapshot, saveProfile, type Profile } from "../lib/profile";

const STEPS = ["language", "intro1", "intro2", "intro3", "place", "cost", "contact", "done"] as const;
type Step = (typeof STEPS)[number];
const QUESTION_COUNT = STEPS.length - 1;
const INTRO_STEPS: Step[] = ["intro1", "intro2", "intro3"];

/**
 * First-run setup, after Sprout's tutorial: language first, then three short
 * scenes where Raahi shows how Annu works (ask in your own words,
 * emergencies go first, proof then distance), then one question per screen.
 * Raahi asks each, every step can be skipped, and the whole thing can be skipped.
 * It's offered once and never stands between anyone and search or the
 * emergency screen; "Call 108" stays in the header throughout.
 *
 * Only questions whose answers change something are asked: language, where
 * to search from, whether government hospitals come first, and who to call in
 * an emergency. Distance is not asked: the recommender weighs it for each kind
 * of care. Answers are saved as they're given, so leaving half-way loses nothing.
 */
export function Onboarding() {
  const { t, lang, setLang } = useI18n();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const session = useSession();
  const again = params.has("again");
  const [step, setStep] = useState<Step>("language");
  const [draft, setDraft] = useState<Profile>(profileSnapshot);
  const cardRef = useRef<HTMLElement>(null);
  const index = STEPS.indexOf(step);

  // Someone who already finished goes straight home, unless they asked to redo it.
  useEffect(() => {
    if (profileSnapshot().onboardingDone && !again) navigate("/", { replace: true });
  }, [again, navigate]);

  // Move focus to each new question so screen readers announce it.
  useEffect(() => {
    cardRef.current?.querySelector<HTMLElement>("h1")?.focus();
  }, [step]);

  function update(patch: Partial<Profile>) {
    setDraft((current) => ({ ...current, ...patch }));
    saveProfile(patch);
  }

  // Each new question slides in; the progress bar grows to match.
  const next = () => withTransition(() => setStep(STEPS[Math.min(index + 1, STEPS.length - 1)]), "step");

  function finish() {
    saveProfile({ onboardingDone: true });
  }

  function skipAll() {
    saveProfile({ onboardingDone: true });
    navigate("/", { replace: true });
  }

  return (
    <div className="app-shell">
      <Header />
      <main className="flow">
        <div className="flow-inner">
          {step !== "done" && (
            <div className="flow-top">
              <div className="flow-progress">
                <span>{t.obStep(index + 1, QUESTION_COUNT)}</span>
                <span
                  className="flow-bar"
                  aria-hidden="true"
                  style={{ "--progress": (index + 1) / QUESTION_COUNT } as React.CSSProperties}
                />
              </div>
              <button type="button" className="link-button" onClick={skipAll}>
                {t.obSkipAll}
              </button>
            </div>
          )}

          <section className="flow-card" ref={cardRef} aria-live="polite">
            {step === "language" && (
              <Question ask={t.obLangAsk} hint={t.obLangHint}>
                <div className="choice-grid">
                  {(
                    [
                      ["en", "English"],
                      ["hi", "हिंदी"],
                    ] as Array<[Lang, string]>
                  ).map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      lang={value}
                      className="choice"
                      aria-pressed={lang === value}
                      onClick={() => {
                        setLang(value);
                        next();
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </Question>
            )}

            {INTRO_STEPS.includes(step) && (
              <IntroScene
                index={INTRO_STEPS.indexOf(step)}
                onNext={next}
                onSkip={() => withTransition(() => setStep("place"), "step")}
              />
            )}

            {step === "place" && (
              <PlaceStep
                value={draft.location}
                onSave={(location) => {
                  update({ location });
                  next();
                }}
                onSkip={next}
              />
            )}

            {step === "cost" && (
              <Question ask={t.obCostAsk}>
                <div className="choice-grid choice-grid-stack">
                  {(
                    [
                      [true, t.obCostYes],
                      [false, t.obCostNo],
                    ] as Array<[boolean, string]>
                  ).map(([value, label]) => (
                    <button
                      key={String(value)}
                      type="button"
                      className="choice"
                      aria-pressed={draft.governmentFirst === value}
                      onClick={() => {
                        update({ governmentFirst: value });
                        next();
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <SkipQuestion onClick={next} />
              </Question>
            )}

            {step === "contact" && (
              <ContactStep
                value={draft.emergencyContact}
                onSave={(emergencyContact) => {
                  update({ emergencyContact });
                  finish();
                  next();
                }}
                onSkip={() => {
                  finish();
                  next();
                }}
              />
            )}

            {step === "done" && (
              <div className="flow-done">
                <RaahiSays size={72}>
                  <h1 tabIndex={-1}>{t.obDoneTitle}</h1> {t.obDoneBody}
                </RaahiSays>
                <dl className="summary-list">
                  <div>
                    <dt>{t.obSumPlace}</dt>
                    <dd>{draft.location ?? t.obNotSet}</dd>
                  </div>
                  <div>
                    <dt>{t.obSumCost}</dt>
                    <dd>
                      {draft.governmentFirst === null
                        ? t.obNotSet
                        : draft.governmentFirst
                          ? t.obSumCostFirst
                          : t.obSumCostNormal}
                    </dd>
                  </div>
                  <div>
                    <dt>{t.obSumContact}</dt>
                    <dd>
                      {draft.emergencyContact
                        ? `${draft.emergencyContact.name}, ${formatPhone(draft.emergencyContact.phone)}`
                        : t.obNotSet}
                    </dd>
                  </div>
                </dl>
                <div className="flow-actions">
                  <button type="button" className="primary-button flow-primary" onClick={() => navigate("/")}>
                    {t.obDoneFind}
                    <ArrowRight size={18} aria-hidden="true" />
                  </button>
                  {!session && (
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => navigate("/sign-in?return_to=/")}
                    >
                      {t.obDoneSignIn}
                    </button>
                  )}
                </div>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

function Question({ ask, hint, children }: { ask: string; hint?: string; children: React.ReactNode }) {
  return (
    <>
      <RaahiSays size={64}>
        <h1 tabIndex={-1}>{ask}</h1>
      </RaahiSays>
      {hint && <p className="flow-hint">{hint}</p>}
      <div className="flow-answer">{children}</div>
    </>
  );
}

function SkipQuestion({ onClick }: { onClick: () => void }) {
  const { t } = useI18n();
  return (
    <button type="button" className="link-button flow-skip" onClick={onClick}>
      {t.obSkipQuestion}
    </button>
  );
}

function PlaceStep({
  value,
  onSave,
  onSkip,
}: {
  value: string | null;
  onSave: (location: string) => void;
  onSkip: () => void;
}) {
  const { t } = useI18n();
  const [text, setText] = useState(value ?? "");
  const [geo, setGeo] = useState<"idle" | "locating" | "error">("idle");
  const matches = text.trim()
    ? locations.filter((option) =>
        `${option.name} ${option.region}`.toLowerCase().includes(text.trim().toLowerCase()),
      )
    : locations;

  function useMyLocation() {
    if (!navigator.geolocation) return setGeo("error");
    setGeo("locating");
    navigator.geolocation.getCurrentPosition(
      () => {
        setGeo("idle");
        onSave(t.currentLocation);
      },
      () => setGeo("error"),
      { timeout: 8000 },
    );
  }

  return (
    <Question ask={t.obPlaceAsk} hint={t.obPlaceHint}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (text.trim()) onSave(text.trim());
        }}
      >
        <label className="field-label" htmlFor="ob-place">
          {t.placeLabel}
        </label>
        <div className="text-field">
          <input
            id="ob-place"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={t.placePlaceholder}
            autoComplete="address-level2"
            enterKeyHint="next"
            list="ob-place-options"
          />
          <button type="button" className="locate-button" onClick={useMyLocation} aria-label={t.useLocation}>
            {geo === "locating" ? <LoaderCircle className="spin" size={18} /> : <Crosshair size={18} />}
          </button>
        </div>
        <datalist id="ob-place-options">
          {matches.map((option) => (
            <option key={option.id} value={`${option.name}, ${option.region}`} />
          ))}
        </datalist>
        {geo === "error" && <p className="field-message">{t.locationError}</p>}
        <div className="flow-actions">
          <button type="submit" className="primary-button flow-primary" disabled={!text.trim()}>
            {t.obNext}
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        </div>
      </form>
      <SkipQuestion onClick={onSkip} />
    </Question>
  );
}

function ContactStep({
  value,
  onSave,
  onSkip,
}: {
  value: Profile["emergencyContact"];
  onSave: (contact: NonNullable<Profile["emergencyContact"]>) => void;
  onSkip: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(value?.name ?? "");
  const [phone, setPhone] = useState(value?.phone ?? "");
  const [touched, setTouched] = useState(false);
  const digits = phone.replace(/\D/g, "").replace(/^(91|0)(?=\d{10}$)/, "");
  const valid = isValidMobile(digits);

  return (
    <Question ask={t.obContactAsk} hint={t.obContactHint}>
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          setTouched(true);
          if (valid) onSave({ name: name.trim() || formatPhone(digits), phone: digits });
        }}
      >
        <label className="field-label" htmlFor="ob-contact-name">
          {t.obContactName}
        </label>
        <div className="text-field">
          <input
            id="ob-contact-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t.obContactNamePlaceholder}
            autoComplete="off"
            enterKeyHint="next"
            maxLength={40}
          />
        </div>
        <label className="field-label" htmlFor="ob-contact-phone">
          {t.obContactPhone}
        </label>
        <div className="text-field phone-field">
          <span aria-hidden="true">+91</span>
          <input
            id="ob-contact-phone"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            onBlur={() => setTouched(true)}
            inputMode="numeric"
            autoComplete="off"
            enterKeyHint="done"
            maxLength={14}
            aria-invalid={touched && !valid}
            aria-describedby={touched && !valid ? "ob-contact-error" : undefined}
          />
        </div>
        {touched && !valid && (
          <p className="field-message" id="ob-contact-error">
            {t.obContactError}
          </p>
        )}
        <div className="flow-actions">
          <button type="submit" className="primary-button flow-primary">
            <Check size={18} aria-hidden="true" />
            {t.obNext}
          </button>
        </div>
      </form>
      <SkipQuestion onClick={onSkip} />
    </Question>
  );
}
