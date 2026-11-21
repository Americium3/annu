import {
  ArrowDownWideNarrow,
  ChevronDown,
  LoaderCircle,
  Map,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { sortFacilities } from "../data/demo";
import { useMediaQuery } from "../hooks/useMediaQuery";
import type {
  FacilityRecommendation,
  QueryContext,
  RankingMode,
  RecommendationResponse,
} from "../types";
import { FacilityCard } from "./FacilityCard";
import { FacilityDetail } from "./FacilityDetail";
import { FacilityMap } from "./FacilityMap";

interface ResultsViewProps {
  data?: RecommendationResponse;
  isLoading: boolean;
  rankingMode: RankingMode;
  onRankingModeChange: (mode: RankingMode) => void;
  selectedId?: string;
  onSelectedIdChange: (id?: string) => void;
}

const rankingOptions: Array<{ value: RankingMode; label: string }> = [
  { value: "best_match", label: "Best match" },
  { value: "nearest", label: "Nearest" },
  { value: "most_evidence", label: "Most evidence" },
];

function LoadingResults() {
  return (
    <div className="results-loading" aria-live="polite" aria-busy="true">
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
      <span className="loading-caption">
        <LoaderCircle className="spin" size={16} />
        Comparing service evidence and location confidence
      </span>
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
  const searchRadius = data?.queryContext.searchParameters.radiusKm ?? 10;
  const [maxDistance, setMaxDistance] = useState(searchRadius);
  const [highConfidenceOnly, setHighConfidenceOnly] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [detailId, setDetailId] = useState<string>();
  const isMobileLayout = useMediaQuery("(max-width: 680px)");

  const facilities = useMemo(() => {
    if (!data) return [];
    const filtered = data.results.filter((facility) => {
      const withinDistance = facility.distanceKm <= maxDistance;
      const confidenceMatches =
        !highConfidenceOnly || facility.confidence === "high";
      return withinDistance && confidenceMatches;
    });
    return sortFacilities(filtered, rankingMode).map((facility, index) => ({
      ...facility,
      rank: index + 1,
    }));
  }, [data, highConfidenceOnly, maxDistance, rankingMode]);

  // A new search resets the distance filter to the radius the backend actually searched (it may have widened).
  useEffect(() => {
    setMaxDistance(searchRadius);
  }, [data, searchRadius]);

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

  return (
    <>
      <section className="results-section" aria-labelledby="results-heading">
        <div className="results-header">
          <div>
            <span className="results-eyebrow">
              <Sparkles size={14} />
              Evidence-first recommendations
            </span>
            <h2 id="results-heading">
              {data ? (
                <>
                  Care options for{" "}
                  <span>{data.queryContext.service.displayName.toLowerCase()}</span>
                </>
              ) : (
                "Finding care options"
              )}
            </h2>
            {data && (
              <p className="results-context">
                Near {data.queryContext.location.resolvedName}
                {data.queryContext.location.state ? `, ${data.queryContext.location.state}` : ""} · within{" "}
                {data.queryContext.searchParameters.radiusKm} km ·{" "}
                {data.metadata.returnedCount} candidates
              </p>
            )}
            {data && data.metadata.warnings.length > 0 && (
              <ul className="results-notices">
                {data.metadata.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            )}
          </div>
          <div className="results-status">
            <span className="status-live">
              <i />
              Explainable ranking
            </span>
            <span>{data?.metadata.rankingVersion ?? "Rules model"}</span>
          </div>
        </div>

        <div className="results-toolbar">
          <div className="ranking-tabs" role="group" aria-label="Ranking priority">
            <span className="toolbar-label">
              <ArrowDownWideNarrow size={15} />
              Rank by
            </span>
            {rankingOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                className={rankingMode === option.value ? "is-active" : ""}
                onClick={() => onRankingModeChange(option.value)}
                aria-pressed={rankingMode === option.value}
              >
                {option.label}
              </button>
            ))}
          </div>
          <button
            className={`filter-button ${filtersOpen ? "is-active" : ""}`}
            type="button"
            aria-expanded={filtersOpen}
            onClick={() => setFiltersOpen((open) => !open)}
          >
            <SlidersHorizontal size={16} />
            Filters
            {highConfidenceOnly && <span className="filter-count">1</span>}
            <ChevronDown size={14} />
          </button>
          {filtersOpen && (
            <div className="filter-popover">
              <div className="filter-heading">
                <strong>Narrow results</strong>
                <button
                  type="button"
                  onClick={() => {
                    setMaxDistance(searchRadius);
                    setHighConfidenceOnly(false);
                  }}
                >
                  Reset
                </button>
              </div>
              <label className="range-label">
                <span>
                  Maximum distance <strong>{maxDistance} km</strong>
                </span>
                <input
                  type="range"
                  min="1"
                  max={Math.max(15, Math.ceil(searchRadius))}
                  step="1"
                  value={maxDistance}
                  onChange={(event) => setMaxDistance(Number(event.target.value))}
                />
              </label>
              <label className="toggle-label">
                <span>
                  <strong>High confidence only</strong>
                  <small>Official or strong corroborating evidence</small>
                </span>
                <input
                  type="checkbox"
                  checked={highConfidenceOnly}
                  onChange={(event) => setHighConfidenceOnly(event.target.checked)}
                />
                <i />
              </label>
            </div>
          )}
        </div>

        <div className="mobile-view-toggle" role="group" aria-label="Switch result view">
          <button
            type="button"
            className={mobileView === "list" ? "is-active" : ""}
            onClick={() => setMobileView("list")}
          >
            List
          </button>
          <button
            type="button"
            className={mobileView === "map" ? "is-active" : ""}
            onClick={() => setMobileView("map")}
          >
            <Map size={15} /> Map
          </button>
        </div>

        <div className="results-layout">
          <div className={`results-list-wrap mobile-${mobileView}`}>
            <div className="list-heading">
              <span>
                {isLoading ? "Searching…" : `${facilities.length} facilities`}
              </span>
              <span>
                {data?.metadata.funnel
                  ? `${data.metadata.funnel.datasetProviders} in dataset · ${data.metadata.funnel.withinRadius} within ${data.metadata.funnel.radiusKm} km`
                  : "Sample results"}
              </span>
            </div>
            {isLoading ? (
              <LoadingResults />
            ) : facilities.length > 0 ? (
              <div className="results-list">
                {facilities.map((facility) => (
                  <FacilityCard
                    key={facility.id}
                    facility={facility}
                    selected={selectedId === facility.id}
                    onSelect={() => onSelectedIdChange(facility.id)}
                    onOpen={() => setDetailId(facility.id)}
                  />
                ))}
              </div>
            ) : (
              <div className="empty-results">
                <span className="empty-icon">
                  <SlidersHorizontal size={22} />
                </span>
                <h3>
                  {data && data.results.length === 0
                    ? "No supported facility found"
                    : "No facilities match these filters"}
                </h3>
                <p>
                  {data && data.results.length === 0
                    ? data.metadata.warnings[0]
                    : "Increase the distance or remove the confidence filter."}
                </p>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => {
                    setMaxDistance(searchRadius);
                    setHighConfidenceOnly(false);
                  }}
                >
                  Clear filters
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
      <FacilityDetail facility={detailFacility} onClose={() => setDetailId(undefined)} />
    </>
  );
}
