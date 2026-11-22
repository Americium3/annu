import { List, Map } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { sortFacilities } from "../data/demo";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { isGovernment, useI18n } from "../i18n";
import type { RankingMode, RecommendationResponse } from "../types";
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
  /** From setup: list government hospitals before private ones. */
  governmentFirst?: boolean;
}

function LoadingResults() {
  const { t } = useI18n();
  return (
    <div className="results-loading" aria-live="polite" aria-busy="true">
      <RaahiSays mood="thinking" size={48}>
        {t.loadingRaahi}
      </RaahiSays>
      {[0, 1, 2].map((item) => (
        <div className="skeleton-card" key={item}>
          <div className="skeleton skeleton-rank" />
          <div className="skeleton-content">
            <div className="skeleton skeleton-title" />
            <div className="skeleton skeleton-line skeleton-line-short" />
            <div className="skeleton skeleton-line" />
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Results answer "which hospital should I go to?": the best choice first with
 * one filled action, the alternatives below, and two controls that change the
 * answer (best match vs nearest, government only). Everything else is behind
 * "Why this hospital?".
 */
export function ResultsView({
  data,
  isLoading,
  rankingMode,
  onRankingModeChange,
  selectedId,
  onSelectedIdChange,
  governmentFirst = false,
}: ResultsViewProps) {
  const [mobileView, setMobileView] = useState<"list" | "map">("list");
  const [governmentOnly, setGovernmentOnly] = useState(false);
  const [detailId, setDetailId] = useState<string>();
  const isMobileLayout = useMediaQuery("(max-width: 680px)");
  const { t } = useI18n();

  const facilities = useMemo(() => {
    if (!data) return [];
    const filtered = data.results.filter(
      (facility) => !governmentOnly || isGovernment(facility.operatorType),
    );
    const sorted = sortFacilities(filtered, rankingMode);
    // A stable partition keeps the chosen order inside each group.
    const ordered = governmentFirst
      ? [
          ...sorted.filter((facility) => isGovernment(facility.operatorType)),
          ...sorted.filter((facility) => !isGovernment(facility.operatorType)),
        ]
      : sorted;
    return ordered.map((facility, index) => ({ ...facility, rank: index + 1 }));
  }, [data, governmentFirst, governmentOnly, rankingMode]);

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

  const service = data?.queryContext.service.displayName ?? "";
  const sortOptions: Array<{ value: RankingMode; label: string }> = [
    { value: "best_match", label: t.sortBest },
    { value: "nearest", label: t.sortNearest },
  ];

  return (
    <>
      <section className="results-section" aria-labelledby="results-heading">
        <h2 id="results-heading" className="results-title">
          {data && !isLoading
            ? t.resultsTitle(facilities.length, service, data.queryContext.location.resolvedName)
            : t.resultsSearching}
        </h2>

        <div className="results-toolbar">
          <div className="segmented" role="group" aria-label={t.sortBy}>
            {sortOptions.map((option) => (
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
          <label className="inline-check">
            <input
              type="checkbox"
              checked={governmentOnly}
              onChange={(event) => setGovernmentOnly(event.target.checked)}
            />
            {t.governmentOnly}
          </label>
          <div className="segmented mobile-view-toggle" role="group" aria-label={`${t.viewList} / ${t.viewMap}`}>
            <button type="button" aria-pressed={mobileView === "list"} onClick={() => setMobileView("list")}>
              <List size={16} aria-hidden="true" /> {t.viewList}
            </button>
            <button type="button" aria-pressed={mobileView === "map"} onClick={() => setMobileView("map")}>
              <Map size={16} aria-hidden="true" /> {t.viewMap}
            </button>
          </div>
        </div>

        <div className="results-layout">
          <div className={`results-list-wrap mobile-${mobileView}`}>
            {isLoading ? (
              <LoadingResults />
            ) : facilities.length > 0 ? (
              <div className="results-list">
                {facilities.map((facility, index) => (
                  <FacilityCard
                    key={facility.id}
                    facility={facility}
                    service={service}
                    primary={index === 0}
                    selected={selectedId === facility.id}
                    onSelect={() => onSelectedIdChange(facility.id)}
                    onOpen={() => setDetailId(facility.id)}
                  />
                ))}
              </div>
            ) : (
              <div className="empty-results">
                <RaahiSays mood="concerned" size={56}>
                  <strong>{t.emptyTitle}</strong> {t.emptyBody}
                </RaahiSays>
                <button className="secondary-button" type="button" onClick={() => setGovernmentOnly(false)}>
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
