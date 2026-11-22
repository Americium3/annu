import { ArrowLeft, TriangleAlert } from "lucide-react";
import { useEffect, useLayoutEffect, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Footer } from "../components/Footer";
import { Header } from "../components/Header";
import { Raahi } from "../components/Raahi";
import { ResultsView } from "../components/ResultsView";
import { Signposts } from "../components/Signposts";
import { TrustSection } from "../components/TrustSection";
import { useI18n } from "../i18n";
import { withTransition } from "../lib/motion";
import { useProfile } from "../lib/profile";
import { useSearchSession } from "../lib/session";

/**
 * The results, on their own page. Arriving from the conversation, Raahi and the
 * signposts glide into the summary bar (shared view-transition names) and the
 * results rise in below. Opened from a link (/results?care=&place=&urgency=),
 * it searches by itself. Back returns to the same conversation.
 */
export function Results() {
  const s = useSearchSession();
  const { t } = useI18n();
  const profile = useProfile();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string>();
  const care = params.get("care") ?? "";
  const place = params.get("place") ?? "";
  const lat = params.get("lat");
  const lon = params.get("lon");
  const urgency = Number(params.get("urgency") ?? 4) || 4;
  const showing = s.data?.queryContext.service.canonicalId;

  // A new page starts at the top (the conversation may have been scrolled far down).
  useLayoutEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, []);

  useEffect(() => {
    if (!care) {
      navigate("/", { replace: true });
      return;
    }
    // Already searched in the conversation: nothing to load.
    if (s.data && (showing === care || s.answer?.care?.id === care)) return;
    void s.load(
      {
        serviceText: care,
        locationText: place,
        coordinates: lat && lon ? { latitude: Number(lat), longitude: Number(lon) } : undefined,
        urgency,
      },
      care,
      place,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [care, place, lat, lon, urgency]);

  function back() {
    // History has the conversation behind us when we came from it; a shared link starts a new one.
    withTransition(() => (location.key !== "default" ? navigate(-1) : navigate("/")), "to-conversation");
  }

  const answer = s.answer;
  const travel = s.data?.queryContext.searchParameters.travelKm;
  const top = s.data?.results[0]?.distanceKm;
  const urgentFar = urgency === 3 && top !== undefined && travel !== undefined && top > 2 * travel;

  return (
    <div className="app-shell">
      <Header />
      <main>
        <section className="results-hero" aria-label={t.understoodTitle}>
          <div className="results-hero-inner">
            <button type="button" className="back-to-chat" onClick={back}>
              <ArrowLeft size={18} aria-hidden="true" />
              <span className="raahi-mark is-current" style={{ viewTransitionName: "raahi-guide" } as React.CSSProperties}>
                <Raahi size={36} mood="happy" />
              </span>
              <span>{t.askAgain}</span>
            </button>
            {answer && <Signposts answer={answer} shared compact />}
          </div>
          {urgentFar && (
            <p className="results-hero-warning">
              <TriangleAlert size={16} aria-hidden="true" />
              {t.urgentFar(top!.toFixed(0))} <a href="tel:108">{t.call108Short}</a>
            </p>
          )}
        </section>
        <ResultsView
          data={s.data}
          isLoading={s.busy && !s.data}
          judging={s.judging}
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
