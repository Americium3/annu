import { List, Map } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { orderFacilities } from "../data/demo";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { isGovernment, useI18n } from "../i18n";
import { withTransition } from "../lib/motion";
import { RADIUS_OPTIONS } from "../lib/profile";
import type { RecommendationResponse } from "../types";
import { BoardRow, TopPick } from "./FacilityCard";
import { FacilityDetail } from "./FacilityDetail";
import { FacilityMap } from "./FacilityMap";
import { RaahiSays } from "./Raahi";
import { Segmented } from "./Segmented";

type SortMode = "best" | "nearest";

interface ResultsViewProps {
  data?: RecommendationResponse;
  isLoading: boolean;
  selectedId?: string;
  onSelectedIdChange: (id?: string) => void;
  /** Distance cap from the search sentence; 0 = any distance. */
  radiusKm: number;
  onRadiusChange: (km: number) => void;
  /** From setup: list government hospitals before private ones. */
  governmentFirst: boolean;
}

function LoadingResults() {
  const { t } = useI18n();
  return (
    <div className="results-loading" aria-live="polite" aria-busy="true">
      <RaahiSays mood="thinking" size={48}>
        {t.loadingRaahi}
      </RaahiSays>
      <div className="skeleton skeleton-pick" />
      {[0, 1, 2].map((item) => (
        <div className="skeleton skeleton-row" key={item} style={{ "--i": item } as React.CSSProperties} />
      ))}
    </div>
  );
}

/**
 * Results answer "which hospital should I go to?". The recommender's list is
 * the starting point; the person's own choices (distance, nearest first,
 * government only, government first) are applied on top of it, in the
 * browser, and every change animates rows to their new places.
 */
export function ResultsView({
  data,
  isLoading,
  selectedId,
  onSelectedIdChange,
  radiusKm,
  onRadiusChange,
  governmentFirst,
}: ResultsViewProps) {
  const [mobileView, setMobileView] = useState<"list" | "map">("list");
  const [sort, setSort] = useState<SortMode>("best");
  const [governmentOnly, setGovernmentOnly] = useState(false);
  const [detailId, setDetailId] = useState<string>();
  const isMobileLayout = useMediaQuery("(max-width: 680px)");
  const { t } = useI18n();

  const ordered = useMemo(() => {
    if (!data) return [];
    const base = orderFacilities(data.results);
    return sort === "nearest" ? [...base].sort((a, b) => a.distanceKm - b.distanceKm) : base;
  }, [data, sort]);

  const facilities = useMemo(() => {
    const filtered = ordered.filter(
      (facility) =>
        (radiusKm === 0 || facility.distanceKm <= radiusKm) &&
        (!governmentOnly || isGovernment(facility.operatorType)),
    );
    // Stable partition: the chosen order still holds inside each group.
    const arranged = governmentFirst
      ? [
          ...filtered.filter((facility) => isGovernment(facility.operatorType)),
          ...filtered.filter((facility) => !isGovernment(facility.operatorType)),
        ]
      : filtered;
    return arranged.map((facility, index) => ({ ...facility, rank: index + 1 }));
  }, [governmentFirst, governmentOnly, ordered, radiusKm]);

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
  const [top, ...rest] = facilities;

  // Why the list is empty, and the one tap that fixes it.
  const nearestHidden = ordered
    .filter((facility) => !governmentOnly || isGovernment(facility.operatorType))
    .reduce<number | null>(
      (min, facility) => (min === null ? facility.distanceKm : Math.min(min, facility.distanceKm)),
      null,
    );
  const widenTo = nearestHidden !== null ? (RADIUS_OPTIONS.find((km) => km > 0 && km >= nearestHidden) ?? 0) : 0;
  const noGovernmentAtAll =
    governmentOnly && ordered.length > 0 && !ordered.some((facility) => isGovernment(facility.operatorType));

  return (
    <>
      <section className="results-section" aria-labelledby="results-heading">
        <header className="results-head">
          <h2 id="results-heading" className="results-title">
            {data && !isLoading
              ? t.resultsTitle(facilities.length, service, data.queryContext.location.resolvedName)
              : t.resultsSearching}
          </h2>
          <div className="results-controls">
            <Segmented<SortMode>
              label={t.sortBy}
              value={sort}
              onChange={(value) => withTransition(() => setSort(value), "reorder")}
              options={[
                { value: "best", label: t.sortBest },
                { value: "nearest", label: t.sortNearest },
              ]}
            />
            <label className="switch">
              <input
                type="checkbox"
                checked={governmentOnly}
                onChange={(event) => {
                  const checked = event.target.checked;
                  withTransition(() => setGovernmentOnly(checked), "reorder");
                }}
              />
              <span className="switch-track" aria-hidden="true" />
              {t.governmentOnly}
            </label>
            <Segmented<"list" | "map">
              className="mobile-view-toggle"
              label={`${t.viewList} / ${t.viewMap}`}
              value={mobileView}
              onChange={(value) => withTransition(() => setMobileView(value))}
              options={[
                {
                  value: "list",
                  label: (
                    <>
                      <List size={16} aria-hidden="true" /> {t.viewList}
                    </>
                  ),
                },
                {
                  value: "map",
                  label: (
                    <>
                      <Map size={16} aria-hidden="true" /> {t.viewMap}
                    </>
                  ),
                },
              ]}
            />
          </div>
          {data && data.metadata.warnings.length > 0 && !isLoading && facilities.length > 0 && (
            <ul className="results-notices">
              {data.metadata.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
        </header>

        <div className="results-layout">
          <div className={`results-list-wrap mobile-${mobileView}`}>
            {isLoading ? (
              <LoadingResults />
            ) : top ? (
              <>
                <TopPick
                  nearest={sort === "nearest"}
                  facility={top}
                  service={service}
                  index={0}
                  selected={selectedId === top.id}
                  onSelect={() => onSelectedIdChange(top.id)}
                  onOpen={() => setDetailId(top.id)}
                />
                {rest.length > 0 && (
                  <>
                    <h3 className="board-title">{t.alsoNearby}</h3>
                    <ol className="board">
                      {rest.map((facility, index) => (
                        <BoardRow
                          key={facility.id}
                          facility={facility}
                          service={service}
                          index={index}
                          selected={selectedId === facility.id}
                          onSelect={() => onSelectedIdChange(facility.id)}
                          onOpen={() => setDetailId(facility.id)}
                        />
                      ))}
                    </ol>
                  </>
                )}
              </>
            ) : (
              <div className="empty-results">
                {noGovernmentAtAll ? (
                  <>
                    <RaahiSays mood="concerned" size={56}>
                      <strong>{t.noGovernment}</strong>
                    </RaahiSays>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => withTransition(() => setGovernmentOnly(false), "reorder")}
                    >
                      {t.showAllHospitals}
                    </button>
                  </>
                ) : radiusKm > 0 && nearestHidden !== null ? (
                  <>
                    <RaahiSays mood="concerned" size={56}>
                      <strong>{t.noneWithin(radiusKm, nearestHidden.toFixed(1))}</strong>
                    </RaahiSays>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => withTransition(() => onRadiusChange(widenTo), "reorder")}
                    >
                      {widenTo > 0 ? t.showUpTo(widenTo) : t.showAnyDistance}
                    </button>
                  </>
                ) : (
                  <RaahiSays mood="concerned" size={56}>
                    <strong>{t.emptyTitle}</strong> {data?.metadata.warnings[0] ?? t.emptyBody}
                  </RaahiSays>
                )}
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
