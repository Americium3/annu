import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AskRaahi } from "./components/AskRaahi";
import { EmergencyView, type EmergencyReason } from "./components/EmergencyView";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { RaahiSays } from "./components/Raahi";
import { ResultsView } from "./components/ResultsView";
import { SearchPanel, type SearchValues } from "./components/SearchPanel";
import { TrustSection } from "./components/TrustSection";
import { Understood, type Coordinates } from "./components/Understood";
import { careTerm } from "./data/careTerms";
import { ApiError, ask, getRecommendations, USE_DEMO } from "./lib/api";
import { findDemoLocation } from "./lib/demoApi";
import { useI18n } from "./i18n";
import { withTransition } from "./lib/motion";
import { useProfile } from "./lib/profile";
import { understand } from "./lib/understand";
import type { AskResponse, RecommendationResponse } from "./types";

const DEFAULT_ORIGIN = { latitude: 20.2961, longitude: 85.8245, name: "Bhubaneswar" };

/**
 * Home: one question, "what's happening?", answered in the person's own words.
 *
 * Raahi reads the sentence (backend /api/ask: rules first, then an optional
 * language model), shows what it understood with the exact words behind each
 * part, asks one follow-up only when something is missing, and searches. An
 * emergency score of 80+ skips everything and opens the emergency screen.
 * The older two-blank form stays one tap away ("Pick from a list instead").
 */
function App() {
  const [searchParams, setSearchParams] = useSearchParams();
  const profile = useProfile();
  const { t } = useI18n();
  const [answer, setAnswer] = useState<AskResponse>();
  const [placeCoords, setPlaceCoords] = useState<Coordinates>();
  const [data, setData] = useState<RecommendationResponse>();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError>();
  const [selectedId, setSelectedId] = useState<string>();
  const [reason, setReason] = useState<EmergencyReason>();
  const [mode, setMode] = useState<"ask" | "pick">(searchParams.get("service") ? "pick" : "ask");
  const emergency = searchParams.get("mode") === "emergency";
  const query = searchParams.get("q") ?? "";

  const openEmergency = useCallback(
    (why?: EmergencyReason) => {
      setReason(why);
      const next = new URLSearchParams(searchParams);
      next.set("mode", "emergency");
      withTransition(() => setSearchParams(next), "emergency");
    },
    [searchParams, setSearchParams],
  );

  function closeEmergency() {
    const next = new URLSearchParams(searchParams);
    next.delete("mode");
    withTransition(() => setSearchParams(next), "emergency");
  }

  /** Structured search once care and place are known (from the text, a follow-up, or a change). */
  const search = useCallback(async (current: AskResponse, coords?: Coordinates) => {
    if (!current.care) return withTransition(() => setAnswer({ ...current, next: "ask_care" }), "ask");
    if (!current.place?.text && !coords) return withTransition(() => setAnswer({ ...current, next: "ask_place" }), "ask");
    setIsLoading(true);
    try {
      const results = await getRecommendations({
        serviceText: current.care.id,
        locationText: current.place?.text ?? "",
        coordinates: coords,
        urgency: current.urgency.level,
      });
      withTransition(() => {
        setAnswer({ ...current, next: "results", results });
        setData(results);
        setSelectedId(undefined);
      }, "ask");
      setError(undefined);
    } catch (caught) {
      const failure = caught instanceof ApiError ? caught : new ApiError(String(caught));
      if (failure.field === "location") {
        setAnswer({ ...current, next: "ask_place", placeMessage: failure.message, placeSuggestions: failure.suggestions });
      } else if (failure.field === "service") {
        setAnswer({ ...current, next: "ask_care", care: null, careMessage: failure.message });
      } else setError(failure);
      setData(undefined);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const runAsk = useCallback(
    async (text: string) => {
      setIsLoading(true);
      setError(undefined);
      setSearchParams({ q: text }, { replace: true });
      try {
        const response = await ask({ text, locationText: profile.location ?? "" });
        if (response.next === "emergency") {
          setAnswer(response);
          setData(undefined);
          openEmergency({
            quote: response.urgency.span?.quote,
            score: response.urgency.score,
            crisis: response.urgency.crisis,
            placeText: response.place?.text ?? profile.location ?? undefined,
            text,
          });
          return;
        }
        setPlaceCoords(undefined);
        withTransition(() => {
          setAnswer(response);
          setData(response.results);
          setSelectedId(undefined);
        }, "ask");
      } catch (caught) {
        setError(caught instanceof ApiError ? caught : new ApiError(String(caught)));
        setAnswer(undefined);
        setData(undefined);
      } finally {
        setIsLoading(false);
      }
    },
    [openEmergency, profile.location, setSearchParams],
  );

  // A shared link (?q=...) asks again on load; an old two-blank link (?service=&location=) searches directly.
  useEffect(() => {
    if (query && !emergency) void runAsk(query);
    const service = searchParams.get("service");
    if (service && !query) void runStructured({ service, location: searchParams.get("location") ?? "" });
    // Initial URL hydration only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runStructured(values: SearchValues) {
    setIsLoading(true);
    setSearchParams({ service: values.service, location: values.location }, { replace: true });
    try {
      const results = await getRecommendations({
        serviceText: values.service,
        locationText: values.location,
        coordinates: values.coordinates,
      });
      setAnswer(undefined);
      setData(results);
      setError(undefined);
    } catch (caught) {
      setData(undefined);
      setError(caught instanceof ApiError ? caught : new ApiError(String(caught)));
    } finally {
      setIsLoading(false);
    }
  }

  function pickCare(id: string) {
    if (!answer) return;
    const term = careTerm(id);
    const next: AskResponse = {
      ...answer,
      care: { id, name: term?.en ?? id, nameHi: term?.hi ?? id, source: "picked" },
      careOptions: [],
      careOptionsSpan: undefined,
    };
    void search(next, placeCoords);
  }

  function pickPlace(place: { text: string; coordinates?: Coordinates }) {
    if (!answer) return;
    setPlaceCoords(place.coordinates);
    const next: AskResponse = {
      ...answer,
      place: { text: place.text || null, here: Boolean(place.coordinates), source: "picked" },
      placeMessage: undefined,
      placeSuggestions: undefined,
    };
    void search(next, place.coordinates);
  }

  /** From the emergency screen: "not an emergency" continues as an urgent search for what they asked. */
  function notEmergency() {
    const text = reason?.text ?? answer?.text ?? "";
    const local = understand(text, () => false);
    const urgent: AskResponse = {
      ...local,
      urgency: { ...local.urgency, level: 3, score: 60, emergency: false, label: "urgent" },
      care: local.care ?? (local.careOptions.length ? null : { ...careRefFor("emergency-24x7"), source: "rules" }),
      place: local.place ?? (profile.location ? { text: profile.location, here: false, source: "saved" } : null),
      next: "results",
    };
    closeEmergency();
    void search(urgent);
  }

  if (emergency) {
    const origin = data ? data.queryContext.location : null;
    // Demo data has no geocoder: a demo city named in the message sets where "nearest" is measured from.
    const named = USE_DEMO && reason?.placeText ? findDemoLocation(reason.placeText) : undefined;
    return (
      <div className="app-shell">
        <Header />
        <main>
          <EmergencyView
            origin={named ?? (origin ? { latitude: origin.latitude, longitude: origin.longitude } : DEFAULT_ORIGIN)}
            originName={reason?.placeText ?? origin?.resolvedName ?? profile.location ?? DEFAULT_ORIGIN.name}
            contact={profile.emergencyContact}
            reason={reason}
            onExit={closeEmergency}
            onNotEmergency={reason?.text ? notEmergency : undefined}
          />
        </main>
      </div>
    );
  }

  const asked = Boolean(answer) && mode === "ask";
  const topDistance = data?.results[0]?.distanceKm;

  return (
    <div className="app-shell">
      <Header />
      <main>
        <section className={`hero ${asked ? "hero--asked" : ""}`} aria-labelledby="hero-title">
          <div className="hero-inner">
            <h1 id="hero-title" className="sr-only">
              {t.heroTitle}
            </h1>
            {!asked && (
              <RaahiSays className="hero-raahi" size={150} tappable mood={isLoading ? "thinking" : "happy"}>
                {mode === "ask" ? (
                  t.askRaahi
                ) : profile.onboardingDone ? (
                  t.raahiFill
                ) : (
                  <>
                    {t.raahiSetupPre} <Link to="/welcome">{t.raahiSetupLink}</Link>
                    {t.raahiSetupPost}
                  </>
                )}
              </RaahiSays>
            )}

            <div className="hero-main">
            {mode === "ask" ? (
              <AskRaahi initialText={query} isLoading={isLoading} compact={asked} onAsk={(text) => void runAsk(text)} />
            ) : (
              <SearchPanel
                initialService={searchParams.get("service") ?? ""}
                initialLocation={searchParams.get("location") ?? profile.location ?? ""}
                isLoading={isLoading}
                onSearch={(values) => void runStructured(values)}
              />
            )}

            {asked && answer && (
              <Understood answer={answer} onPickCare={pickCare} onPickPlace={pickPlace} topDistanceKm={topDistance} />
            )}

            <button
              type="button"
              className="link-button mode-switch"
              onClick={() => withTransition(() => setMode(mode === "ask" ? "pick" : "ask"), "ask")}
            >
              {mode === "ask" ? t.askPickInstead : t.askTypeInstead}
            </button>
            {!profile.onboardingDone && mode === "ask" && !asked && (
              <p className="hero-setup">
                {t.askSetupPre} <Link to="/welcome">{t.askSetupLink}</Link>
                {t.askSetupPost}
              </p>
            )}
            </div>
          </div>
        </section>

        {error && (
          <section className="api-error" role="alert">
            <div className="api-error-inner">
              <strong>
                {error.field === "service" ? t.errService : error.field === "location" ? t.errLocation : t.askFailed}
              </strong>
              <p>{error.message}</p>
            </div>
          </section>
        )}
        <ResultsView
          data={data}
          isLoading={isLoading && (mode === "pick" || answer?.next === "results")}
          selectedId={selectedId}
          onSelectedIdChange={setSelectedId}
          governmentFirst={profile.governmentFirst === true}
        />
        <TrustSection />
      </main>
      <Footer />
    </div>
  );
}

function careRefFor(id: string) {
  const term = careTerm(id);
  return { id, name: term?.en ?? id, nameHi: term?.hi ?? id };
}

export default App;
