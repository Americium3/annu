import { List, Map } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { orderFacilities } from "../data/demo";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { useI18n } from "../i18n";
import type { RecommendationResponse } from "../types";
import { FacilityCard } from "./FacilityCard";
import { FacilityDetail } from "./FacilityDetail";
import { FacilityMap } from "./FacilityMap";
import { RaahiSays } from "./Raahi";

interface ResultsViewProps {
  data?: RecommendationResponse;
  isLoading: boolean;
  selectedId?: string;
  onSelectedIdChange: (id?: string) => void;
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
  selectedId,
  onSelectedIdChange,
}: ResultsViewProps) {
  const [mobileView, setMobileView] = useState<"list" | "map">("list");
  const [detailId, setDetailId] = useState<string>();
  const isMobileLayout = useMediaQuery("(max-width: 680px)");
  const { t } = useI18n();

  // Shown exactly in the recommender's order: it owns ranking and radius, the
  // person only says what care and where.
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

  const service = data?.queryContext.service.displayName ?? "";
  return (
    <>
      <section className="results-section" aria-labelledby="results-heading">
        <h2 id="results-heading" className="results-title">
          {data && !isLoading
            ? t.resultsTitle(facilities.length, service, data.queryContext.location.resolvedName)
            : t.resultsSearching}
        </h2>

        {data && data.metadata.warnings.length > 0 && !isLoading && facilities.length > 0 && (
          <ul className="results-notices">
            {data.metadata.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        )}

        <div className="results-toolbar">
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
                  <strong>{t.emptyTitle}</strong> {data?.metadata.warnings[0] ?? t.emptyBody}
                </RaahiSays>
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
