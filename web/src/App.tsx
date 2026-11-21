import { ArrowDown, CheckCircle2, MapPin, ShieldCheck, Sparkles } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { ResultsView } from "./components/ResultsView";
import { SearchPanel, type SearchValues } from "./components/SearchPanel";
import { TrustSection } from "./components/TrustSection";
import { getDemoRecommendations } from "./lib/demoApi";
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
        <section className="hero">
          <div className="hero-grid" aria-hidden="true" />
          <div className="hero-orbit hero-orbit-one" aria-hidden="true" />
          <div className="hero-orbit hero-orbit-two" aria-hidden="true" />
          <div className="hero-content">
            <div className="hero-copy">
              <span className="hero-eyebrow">
                <span className="eyebrow-icon">
                  <ShieldCheck size={14} />
                </span>
                Evidence before assumptions
              </span>
              <h1>
                Find the right care.
                <br />
                See the <em>evidence.</em>
              </h1>
              <p className="hero-lede">
                Search healthcare facilities by service and location. Compare clear, traceable
                reasons — not just a ranking score.
              </p>
              <div className="hero-proof">
                <span>
                  <CheckCircle2 size={15} />
                  Cited service evidence
                </span>
                <span>
                  <CheckCircle2 size={15} />
                  Source quality signals
                </span>
                <span>
                  <CheckCircle2 size={15} />
                  Visible uncertainty
                </span>
              </div>
            </div>

            <aside className="evidence-card" id="evidence">
              <div className="evidence-card-head">
                <div>
                  <span className="mini-eyebrow">
                    <Sparkles size={13} />
                    What makes a result
                  </span>
                  <strong>Evidence you can inspect</strong>
                </div>
                <span className="evidence-score">94</span>
              </div>
              <div className="mini-quote">
                <span>“</span>
                <p>Dedicated dialysis bays with reverse-osmosis water treatment.</p>
              </div>
              <div className="mini-source">
                <span className="source-dot source-official_site" />
                <span>
                  Official site
                  <small>services · dialysis</small>
                </span>
                <span className="mini-verified">
                  <CheckCircle2 size={12} />
                  Strong
                </span>
              </div>
              <div className="mini-divider" />
              <div className="mini-signal-row">
                <span>
                  <MapPin size={14} />
                  High location confidence
                </span>
                <strong>+9</strong>
              </div>
            </aside>
          </div>

          <SearchPanel
            initialService={searchValues.service}
            initialLocation={searchValues.location}
            radiusKm={searchValues.radiusKm}
            isLoading={isLoading}
            onSearch={handleSearch}
          />

          <div className="hero-bottom">
            <a className="scroll-cue" href="#results-heading">
              <span>Explore sample results</span>
              <ArrowDown size={16} />
            </a>
            <p>
              <span className="hero-demo-label">Prototype</span>
              Facilities and source links shown below are illustrative demo data.
            </p>
          </div>
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
