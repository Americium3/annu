import { Ambulance, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { EmergencyView } from "./components/EmergencyView";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { Raahi } from "./components/Raahi";
import { ResultsView } from "./components/ResultsView";
import { SearchPanel, type SearchValues } from "./components/SearchPanel";
import { SetupPrompt } from "./components/SetupPrompt";
import { TrustSection } from "./components/TrustSection";
import { getDemoRecommendations } from "./lib/demoApi";
import { useI18n } from "./i18n";
import { profileSnapshot, useProfile } from "./lib/profile";
import type { RankingMode, RecommendationResponse } from "./types";

const defaultSearch: SearchValues = {
  service: "Kidney dialysis",
  location: "Bhubaneswar, Odisha",
  radiusKm: 10,
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
  const [rankingMode, setRankingMode] = useState<RankingMode>("best_match");
  const [selectedId, setSelectedId] = useState<string>();
  const { t } = useI18n();
  const emergency = searchParams.get("mode") === "emergency";

  function openEmergency() {
    // A real history entry, so the phone's Back button leaves emergency mode.
    const next = new URLSearchParams(searchParams);
    next.set("mode", "emergency");
    setSearchParams(next);
  }

  function closeEmergency() {
    const next = new URLSearchParams(searchParams);
    next.delete("mode");
    setSearchParams(next);
  }

  const urlSearch = useMemo(() => {
    const start = startingSearch();
    return {
      service: searchParams.get("service") || start.service,
      location: searchParams.get("location") || start.location,
      radiusKm: Number(searchParams.get("radius")) || start.radiusKm,
    };
  }, [searchParams]);

  const runSearch = useCallback(
    async (values: SearchValues, mode: RankingMode, replaceUrl = true) => {
      setIsLoading(true);
      setSelectedId(undefined);
      setSearchValues(values);

      if (replaceUrl) {
        setSearchParams(
          {
            service: values.service,
            location: values.location,
            radius: String(values.radiusKm),
          },
          { replace: true },
        );
      }

      const response = await getDemoRecommendations({
        serviceText: values.service,
        locationText: values.location,
        radiusKm: values.radiusKm,
        rankingMode: mode,
        limit: 8,
        coordinates: values.coordinates,
      });

      setData(response);
      setSelectedId(undefined);
      setIsLoading(false);
    },
    [setSearchParams],
  );

  useEffect(() => {
    void runSearch(urlSearch, "best_match", false);
    // Initial URL hydration only; subsequent searches are user-driven.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSearch(values: SearchValues) {
    void runSearch(values, rankingMode);
  }

  function handleRankingChange(mode: RankingMode) {
    setRankingMode(mode);
    setSelectedId(undefined);
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
            {/* Two doors, as on Sprout's landing page: urgent first, then search. */}
            <button className="emergency-door" type="button" onClick={openEmergency}>
              <Ambulance size={26} aria-hidden="true" />
              <span>
                <strong>{t.emergencyDoorTitle}</strong>
                <small>{t.emergencyDoorBody}</small>
              </span>
              <ChevronRight size={20} aria-hidden="true" />
            </button>
            <div className="hero-ask">
              <Raahi size={56} />
              <h1 id="hero-title" className="raahi-bubble">
                {t.raahiAsk}
              </h1>
            </div>
          </div>

          <SearchPanel
            initialService={searchValues.service}
            initialLocation={searchValues.location}
            radiusKm={searchValues.radiusKm}
            isLoading={isLoading}
            onSearch={handleSearch}
          />
          <div className="search-wrap">
            <SetupPrompt />
          </div>
        </section>

        <ResultsView
          data={data}
          isLoading={isLoading}
          rankingMode={rankingMode}
          onRankingModeChange={handleRankingChange}
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

export default App;
