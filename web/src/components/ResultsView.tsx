import {
  LoaderCircle,
  Map,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { orderFacilities } from "../data/demo";
import { useMediaQuery } from "../hooks/useMediaQuery";
import type {
  FacilityRecommendation,
  QueryContext,
  RecommendationResponse,
} from "../types";
import { FacilityCard } from "./FacilityCard";
import { FacilityDetail } from "./FacilityDetail";
import { FacilityMap } from "./FacilityMap";

interface ResultsViewProps {
  data?: RecommendationResponse;
  isLoading: boolean;
  selectedId?: string;
  onSelectedIdChange: (id?: string) => void;
}

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
  selectedId,
  onSelectedIdChange,
}: ResultsViewProps) {
  const [mobileView, setMobileView] = useState<"list" | "map">("list");
  const [detailId, setDetailId] = useState<string>();
  const isMobileLayout = useMediaQuery("(max-width: 680px)");

  // Shown exactly in the recommender's order: no user-side re-ranking or filtering.
  const facilities = useMemo(() => (data ? orderFacilities(data.results) : []), [data]);

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
                <h3>No supported facility found</h3>
                <p>{data?.metadata.warnings[0]}</p>
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
