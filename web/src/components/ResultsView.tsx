import { Info, List, Map } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { orderFacilities } from "../data/demo";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { isGovernment, useI18n } from "../i18n";
import { localizeWarning, searchedFrom, serviceName } from "../lib/localize";
import { withTransition } from "../lib/motion";
import type { RecommendationResponse } from "../types";
import { BoardRow, TopPick } from "./FacilityCard";
import { FacilityDetail } from "./FacilityDetail";
import { FacilityMap } from "./FacilityMap";
import { Raahi, RaahiSays } from "./Raahi";
import { Segmented } from "./Segmented";

type SortMode = "best" | "nearest";

interface ResultsViewProps {
  data?: RecommendationResponse;
  isLoading: boolean;
  selectedId?: string;
  onSelectedIdChange: (id?: string) => void;
  /** From setup: list government hospitals before private ones. */
  governmentFirst: boolean;
  /** The language model is reading the top hospitals' records (second pass). */
  judging?: boolean;
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
 * Results answer "which hospital should I go to?". The recommender's order
 * (evidence strength x closeness) is the starting point; the person's own view
 * choices (nearest first, government only, government first) are applied on
 * top of it, and every change animates rows to their new places.
 */
export function ResultsView({
  data,
  isLoading,
  selectedId,
  onSelectedIdChange,
  governmentFirst,
  judging = false,
}: ResultsViewProps) {
  const [mobileView, setMobileView] = useState<"list" | "map">("list");
  const [sort, setSort] = useState<SortMode>("best");
  const [governmentOnly, setGovernmentOnly] = useState(false);
  const [detailId, setDetailId] = useState<string>();
  const isMobileLayout = useMediaQuery("(max-width: 680px)");
  const { t, lang } = useI18n();

  const ordered = useMemo(() => {
    if (!data) return [];
    const base = orderFacilities(data.results);
    return sort === "nearest" ? [...base].sort((a, b) => a.distanceKm - b.distanceKm) : base;
  }, [data, sort]);

  const facilities = useMemo(() => {
    const filtered = ordered.filter(
      (facility) =>
        !governmentOnly || isGovernment(facility.operatorType),
    );
    // Stable partition: the chosen order still holds inside each group.
    const arranged = governmentFirst
      ? [
          ...filtered.filter((facility) => isGovernment(facility.operatorType)),
          ...filtered.filter((facility) => !isGovernment(facility.operatorType)),
        ]
      : filtered;
    return arranged.map((facility, index) => ({ ...facility, rank: index + 1 }));
  }, [governmentFirst, governmentOnly, ordered]);

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

  const service = data ? serviceName(data, lang) : "";
  const warnings = data ? data.metadata.warnings.map((w) => localizeWarning(w, lang, service)) : [];
  const [top, ...rest] = facilities;

  const noGovernmentAtAll =
    governmentOnly && ordered.length > 0 && !ordered.some((facility) => isGovernment(facility.operatorType));

  return (
    <>
      <section className="results-section" aria-labelledby="results-heading">
        <header className="results-head">
          <div className="results-title-row">
            <h2 id="results-heading" className="results-title">
              {data && !isLoading
                ? t.resultsTitle(facilities.length, service, searchedFrom(data, lang, t.currentLocation))
                : t.resultsSearching}
            </h2>
            {/* The recommender's notes on this search: one tap away, not in the way. */}
            {data && warnings.length > 0 && !isLoading && facilities.length > 0 && (
              <details className="results-about">
                <summary aria-label={t.aboutResults} title={t.aboutResults}>
                  <Info size={18} aria-hidden="true" />
                </summary>
                <ul>
                  {warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
          {data && !isLoading && (judging || data.metadata.judge?.used) && (
            <p className={`judge-status ${judging ? "is-reading" : "is-done"}`} aria-live="polite">
              <Raahi size={22} mood={judging ? "thinking" : "happy"} />
              {judging ? t.judging : t.judgedNote(data.metadata.judge?.judged ?? 0)}
            </p>
          )}
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
                ) : (
                  <RaahiSays mood="concerned" size={56}>
                    <strong>{t.emptyTitle}</strong> {warnings[0] ?? t.emptyBody}
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
