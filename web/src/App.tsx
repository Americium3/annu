import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { RaahiSays } from "./components/Raahi";
import { ResultsView } from "./components/ResultsView";
import { SearchPanel, type SearchValues } from "./components/SearchPanel";
import { TrustSection } from "./components/TrustSection";
import { getDemoRecommendations } from "./lib/demoApi";
import { useI18n } from "./i18n";
import type { RankingMode, RecommendationResponse } from "./types";

const defaultSearch: SearchValues = {
  service: "Kidney dialysis",
  location: "Bhubaneswar, Odisha",
  radiusKm: 10,
};

function App() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<RecommendationResponse>();
  const [isLoading, setIsLoading] = useState(true);
  const [searchValues, setSearchValues] = useState<SearchValues>(defaultSearch);
  const [rankingMode, setRankingMode] = useState<RankingMode>("best_match");
  const [selectedId, setSelectedId] = useState<string>();
  const { t } = useI18n();

  const urlSearch = useMemo(
    () => ({
      service: searchParams.get("service") || defaultSearch.service,
      location: searchParams.get("location") || defaultSearch.location,
      radiusKm: Number(searchParams.get("radius")) || defaultSearch.radiusKm,
    }),
    [searchParams],
  );

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

  return (
    <div className="app-shell">
      <Header />
      <main>
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-inner">
            <div className="hero-copy">
              <h1 id="hero-title">{t.heroTitle}</h1>
              <p className="hero-lede">{t.heroLede}</p>
            </div>
            <RaahiSays className="hero-raahi" size={104}>
              <strong>{t.raahiHello}</strong> {t.raahiIntro}
            </RaahiSays>
          </div>

          <SearchPanel
            initialService={searchValues.service}
            initialLocation={searchValues.location}
            radiusKm={searchValues.radiusKm}
            isLoading={isLoading}
            onSearch={handleSearch}
          />
        </section>

        <ResultsView
          data={data}
          isLoading={isLoading}
          rankingMode={rankingMode}
          onRankingModeChange={handleRankingChange}
          selectedId={selectedId}
          onSelectedIdChange={setSelectedId}
        />
        <TrustSection />
      </main>
      <Footer />
    </div>
  );
}

export default App;
