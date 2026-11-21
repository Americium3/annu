import { ChevronDown, List, Map, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { sortFacilities } from "../data/demo";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { isGovernment, useI18n } from "../i18n";
import type {
  RankingMode,
  RecommendationResponse,
} from "../types";
import { FacilityCard } from "./FacilityCard";
import { FacilityDetail } from "./FacilityDetail";
import { FacilityMap } from "./FacilityMap";
import { RaahiSays } from "./Raahi";

interface ResultsViewProps {
  data?: RecommendationResponse;
  isLoading: boolean;
  rankingMode: RankingMode;
  onRankingModeChange: (mode: RankingMode) => void;
  selectedId?: string;
  onSelectedIdChange: (id?: string) => void;
}

function LoadingResults() {
  const { t } = useI18n();
  return (
    <div className="results-loading" aria-live="polite" aria-busy="true">
      <RaahiSays mood="thinking" size={56}>
        {t.loadingRaahi}
      </RaahiSays>
      {[0, 1, 2].map((item) => (
        <div className="skeleton-card" key={item}>
          <div className="skeleton skeleton-rank" />
          <div className="skeleton-content">
            <div className="skeleton skeleton-title" />
            <div className="skeleton skeleton-line skeleton-line-short" />
            <div className="skeleton skeleton-block" />
            <div className="skeleton skeleton-line" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ResultsView({
  data,
  isLoading,
  rankingMode,
  onRankingModeChange,
  selectedId,
  onSelectedIdChange,
}: ResultsViewProps) {
  const [mobileView, setMobileView] = useState<"list" | "map">("list");
  const [maxDistance, setMaxDistance] = useState(10);
  const [highConfidenceOnly, setHighConfidenceOnly] = useState(false);
  const [governmentOnly, setGovernmentOnly] = useState(false);
  const { t } = useI18n();
  const rankingOptions: Array<{ value: RankingMode; label: string }> = [
    { value: "best_match", label: t.sortBest },
    { value: "nearest", label: t.sortNearest },
    { value: "most_evidence", label: t.sortEvidence },
  ];
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [detailId, setDetailId] = useState<string>();
  const isMobileLayout = useMediaQuery("(max-width: 680px)");

  const facilities = useMemo(() => {
    if (!data) return [];
    const filtered = data.results.filter((facility) => {
      const withinDistance = facility.distanceKm <= maxDistance;
      const confidenceMatches =
        !highConfidenceOnly || facility.confidence === "high";
      const operatorMatches = !governmentOnly || isGovernment(facility.operatorType);
      return withinDistance && confidenceMatches && operatorMatches;
    });
    return sortFacilities(filtered, rankingMode).map((facility, index) => ({
      ...facility,
      rank: index + 1,
    }));
  }, [data, governmentOnly, highConfidenceOnly, maxDistance, rankingMode]);

  const detailFacility = data?.results.find((facility) => facility.id === detailId);

  useEffect(() => {
    if (selectedId && !facilities.some((facility) => facility.id === selectedId)) {
      onSelectedIdChange(facilities[0]?.id);
    }
  }, [facilities, onSelectedIdChange, selectedId]);

  useEffect(() => {
    if (!data) return;
    const heading = document.getElementById("results-heading");
    if (heading && window.scrollY > 420) {
      heading.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [data]);

  if (!data && !isLoading) return null;

  const activeFilters = Number(highConfidenceOnly) + Number(governmentOnly) + Number(maxDistance !== 10);
  const service = data?.queryContext.service.displayName ?? "";
  function resetFilters(distance = 10) {
    setMaxDistance(distance);
    setHighConfidenceOnly(false);
    setGovernmentOnly(false);
  }

  return (
    <>
      <section className="results-section" aria-labelledby="results-heading">
        <div className="results-header">
          <h2 id="results-heading">
            {data && !isLoading
              ? t.resultsTitle(facilities.length, service, data.queryContext.location.resolvedName)
              : t.resultsSearching}
          </h2>
          {data && <p className="results-context">{t.resultsContext(data.queryContext.searchParameters.radiusKm)}</p>}
        </div>

        <div className="results-toolbar">
          <div className="sort-control">
            <span className="toolbar-label" id="sort-label">
              {t.sortBy}
            </span>
            <div className="segmented" role="group" aria-labelledby="sort-label">
              {rankingOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => onRankingModeChange(option.value)}
                  aria-pressed={rankingMode === option.value}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          <div className="filter-wrap">
            <button
              className="filter-button"
              type="button"
              aria-expanded={filtersOpen}
              onClick={() => setFiltersOpen((open) => !open)}
            >
              <SlidersHorizontal size={16} aria-hidden="true" />
              {t.filters}
              {activeFilters > 0 && <span className="filter-count">{activeFilters}</span>}
              <ChevronDown size={15} aria-hidden="true" />
            </button>
            {filtersOpen && (
              <div className="filter-popover">
                <div className="filter-heading">
                  <strong>{t.filtersTitle}</strong>
                  <button type="button" onClick={() => resetFilters()}>
                    {t.reset}
                  </button>
                </div>
                <label className="range-label">
                  <span>
                    {t.maxDistance} <strong>{maxDistance} km</strong>
                  </span>
                  <input
                    type="range"
                    min="2"
                    max="15"
                    step="1"
                    value={maxDistance}
                    onChange={(event) => setMaxDistance(Number(event.target.value))}
                  />
                </label>
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={governmentOnly}
                    onChange={(event) => setGovernmentOnly(event.target.checked)}
                  />
                  <span>
                    <strong>{t.governmentOnly}</strong>
                    <small>{t.governmentHint}</small>
                  </span>
                </label>
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={highConfidenceOnly}
                    onChange={(event) => setHighConfidenceOnly(event.target.checked)}
                  />
                  <span>
                    <strong>{t.highConfidenceOnly}</strong>
                    <small>{t.highConfidenceHint}</small>
                  </span>
                </label>
              </div>
            )}
          </div>
        </div>

        <div className="segmented mobile-view-toggle" role="group" aria-label={`${t.viewList} / ${t.viewMap}`}>
          <button type="button" aria-pressed={mobileView === "list"} onClick={() => setMobileView("list")}>
            <List size={16} aria-hidden="true" /> {t.viewList}
          </button>
          <button type="button" aria-pressed={mobileView === "map"} onClick={() => setMobileView("map")}>
            <Map size={16} aria-hidden="true" /> {t.viewMap}
          </button>
        </div>

        <div className="results-layout">
          <div className={`results-list-wrap mobile-${mobileView}`}>
            {isLoading ? (
              <LoadingResults />
            ) : facilities.length > 0 ? (
              <div className="results-list">
                {facilities.map((facility) => (
                  <FacilityCard
                    key={facility.id}
                    facility={facility}
                    service={service}
                    selected={selectedId === facility.id}
                    onSelect={() => onSelectedIdChange(facility.id)}
                    onOpen={() => setDetailId(facility.id)}
                  />
                ))}
              </div>
            ) : (
              <div className="empty-results">
                <RaahiSays mood="concerned" size={64}>
                  <strong>{t.emptyTitle}</strong> {t.emptyBody}
                </RaahiSays>
                <button className="secondary-button" type="button" onClick={() => resetFilters(15)}>
                  {t.clearFilters}
                </button>
              </div>
            )}
          </div>

          <div className={`map-wrap mobile-${mobileView}`}>
            {(!isMobileLayout || mobileView === "map") && (
              <FacilityMap
                facilities={facilities}
                selectedId={selectedId}
                queryContext={data?.queryContext}
                onSelect={onSelectedIdChange}
                onOpen={setDetailId}
                onClearSelection={() => onSelectedIdChange(undefined)}
              />
            )}
          </div>
        </div>
      </section>
      <FacilityDetail facility={detailFacility} service={service} onClose={() => setDetailId(undefined)} />
    </>
  );
}
