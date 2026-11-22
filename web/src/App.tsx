import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { EmergencyView } from "./components/EmergencyView";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { RaahiSays } from "./components/Raahi";
import { ResultsView } from "./components/ResultsView";
import { SearchPanel, type SearchValues } from "./components/SearchPanel";
import { TrustSection } from "./components/TrustSection";
import { ApiError, getRecommendations } from "./lib/api";
import { useI18n } from "./i18n";
import { withTransition } from "./lib/motion";
import { profileSnapshot, RADIUS_OPTIONS, useProfile } from "./lib/profile";
import type { RecommendationResponse } from "./types";

const defaultSearch: SearchValues = {
  service: "Kidney dialysis",
  location: "Bhubaneswar, Odisha",
  radiusKm: 0,
};

/** Search defaults: the person's saved answers first, then the demo city. */
function startingSearch(): SearchValues {
  const profile = profileSnapshot();
  return {
    service: defaultSearch.service,
    location: profile.location ?? defaultSearch.location,
    radiusKm: profile.radiusKm ?? defaultSearch.radiusKm,
  };
}

function App() {
  const [searchParams, setSearchParams] = useSearchParams();
  const profile = useProfile();
  const [data, setData] = useState<RecommendationResponse>();
  const [isLoading, setIsLoading] = useState(true);
  const [searchValues, setSearchValues] = useState<SearchValues>(startingSearch);
  const [error, setError] = useState<ApiError>();
  const [selectedId, setSelectedId] = useState<string>();
  const { t } = useI18n();
  const emergency = searchParams.get("mode") === "emergency";

  function closeEmergency() {
    const next = new URLSearchParams(searchParams);
    next.delete("mode");
    withTransition(() => setSearchParams(next), "emergency");
  }

  function changeRadius(km: number) {
    setSearchValues((current) => ({ ...current, radiusKm: km }));
    const next = new URLSearchParams(searchParams);
    if (km) next.set("radius", String(km));
    else next.delete("radius");
    setSearchParams(next, { replace: true });
  }

  const urlSearch = useMemo(() => {
    const start = startingSearch();
    return {
      service: searchParams.get("service") || start.service,
      location: searchParams.get("location") || start.location,
      // Only a radius actually in the URL counts; Number(null) would read as 0 ("any").
      radiusKm:
        searchParams.has("radius") && RADIUS_OPTIONS.includes(Number(searchParams.get("radius")))
          ? Number(searchParams.get("radius"))
          : start.radiusKm,
    };
  }, [searchParams]);

  const runSearch = useCallback(
    async (values: SearchValues, replaceUrl = true) => {
      setIsLoading(true);
      setSelectedId(undefined);
      setSearchValues(values);

      if (replaceUrl) {
        setSearchParams(
          {
            service: values.service,
            location: values.location,
            ...(values.radiusKm ? { radius: String(values.radiusKm) } : {}),
          },
          { replace: true },
        );
      }

      try {
        const response = await getRecommendations({
          serviceText: values.service,
          locationText: values.location,
          coordinates: values.coordinates,
        });
        setData(response);
        setError(undefined);
      } catch (caught) {
        setData(undefined);
        setError(caught instanceof ApiError ? caught : new ApiError(String(caught)));
      } finally {
        setSelectedId(undefined);
        setIsLoading(false);
      }
    },
    [setSearchParams],
  );

  useEffect(() => {
    void runSearch(urlSearch, false);
    // Initial URL hydration only; subsequent searches are user-driven.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSearch(values: SearchValues) {
    void runSearch(values);
  }

  if (emergency) {
    return (
      <div className="app-shell">
        <Header />
        <main>
          <EmergencyView
            origin={
              data
                ? { latitude: data.queryContext.location.latitude, longitude: data.queryContext.location.longitude }
                : { latitude: 20.2961, longitude: 85.8245 }
            }
            originName={data?.queryContext.location.resolvedName ?? "Bhubaneswar"}
            contact={profile.emergencyContact}
            onExit={closeEmergency}
          />
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Header />
      <main>
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-inner">
            <h1 id="hero-title" className="sr-only">
              {t.heroTitle}
            </h1>
            <RaahiSays className="hero-raahi" size={150} tappable>
              {profile.onboardingDone ? (
                t.raahiFill
              ) : (
                // The only invitation to set up: part of Raahi's one line, never a banner.
                <>
                  {t.raahiSetupPre} <Link to="/welcome">{t.raahiSetupLink}</Link>
                  {t.raahiSetupPost}
                </>
              )}
            </RaahiSays>
            <SearchPanel
              initialService={searchValues.service}
              initialLocation={searchValues.location}
              radiusKm={searchValues.radiusKm}
              isLoading={isLoading}
              onSearch={handleSearch}
            />
          </div>
        </section>

        {error && (
          <section className="api-error" role="alert">
            <div className="api-error-inner">
              <strong>
                {error.field === "service"
                  ? t.errService
                  : error.field === "location"
                    ? t.errLocation
                    : t.errSearch}
              </strong>
              <p>{error.message}</p>
              {error.suggestions.length > 0 && (
                <p className="error-suggestions">
                  <span>{t.errTry}</span>
                  {error.suggestions.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() =>
                        handleSearch(
                          error.field === "service"
                            ? { ...searchValues, service: suggestion }
                            : { ...searchValues, location: suggestion, coordinates: undefined },
                        )
                      }
                    >
                      {suggestion}
                    </button>
                  ))}
                </p>
              )}
            </div>
          </section>
        )}
        <ResultsView
          data={data}
          isLoading={isLoading}
          selectedId={selectedId}
          onSelectedIdChange={setSelectedId}
          radiusKm={searchValues.radiusKm}
          onRadiusChange={changeRadius}
          governmentFirst={profile.governmentFirst === true}
        />
        <TrustSection />
      </main>
      <Footer />
    </div>
  );
}

export default App;
