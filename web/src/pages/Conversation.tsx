import { ArrowRight, MapPinned } from "lucide-react";
import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AskRaahi } from "../components/AskRaahi";
import { EmergencyView } from "../components/EmergencyView";
import { Header } from "../components/Header";
import { Raahi } from "../components/Raahi";
import { SearchPanel } from "../components/SearchPanel";
import { Signposts } from "../components/Signposts";
import { CarePicker, PlacePicker, SaidText } from "../components/Understood";
import { careName } from "../data/careTerms";
import { useI18n } from "../i18n";
import { USE_DEMO } from "../lib/api";
import { findDemoLocation } from "../lib/demoApi";
import { placeName, serviceName } from "../lib/localize";
import { withTransition } from "../lib/motion";
import { useProfile } from "../lib/profile";
import { resultsUrl, useSearchSession, type Exchange } from "../lib/session";
import type { AskResponse } from "../types";

const DEFAULT_ORIGIN = { latitude: 20.2961, longitude: 85.8245, name: "Bhubaneswar" };
const AUTO_MS = 2600;

/**
 * The first page: a conversation with Raahi, and nothing else. It is drawn as
 * a trail (Raahi is "the traveller on the path"): each thing the person says is
 * a footstep on the right, each reply is a stop where Raahi stands, and what
 * Raahi understood is planted along the trail as signposts. When a match is
 * found the trail runs on to a destination marker and the page moves to the
 * results, the signposts and Raahi gliding into the results page's summary bar.
 */
export function Conversation() {
  const s = useSearchSession();
  const { t } = useI18n();
  const profile = useProfile();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [mode, setMode] = useState<"ask" | "pick">("ask");
  const [editing, setEditing] = useState<"care" | "place" | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const emergency = params.get("mode") === "emergency";
  const last = s.exchanges[s.exchanges.length - 1];
  // Coming Back from the results must not bounce forward again: only exchanges settled on this visit move on.
  const seenOnMount = useRef(last?.id ?? 0);

  // Back from the results: show the end of the conversation, where the person left it.
  useLayoutEffect(() => {
    if (s.exchanges.length) endRef.current?.scrollIntoView({ block: "end" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function goResults(answer: AskResponse) {
    withTransition(() => navigate(resultsUrl(answer, s.coords)), "to-results");
  }

  function openEmergency() {
    withTransition(() => navigate("/?mode=emergency"), "emergency");
  }

  async function submit(text: string) {
    setEditing(null);
    const response = await s.ask(text);
    if (response?.next === "emergency") openEmergency();
  }

  // A shared link (?q=...) asks on arrival.
  useEffect(() => {
    const q = params.get("q");
    if (q && !s.exchanges.length && !emergency) void submit(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A match found on this visit: a beat to read Raahi's line, then on to the results.
  useEffect(() => {
    const answer = last?.answer;
    if (!last || last.id <= seenOnMount.current || last.status !== "done" || answer?.next !== "results") return;
    if (!answer.results?.results.length) return;
    const timer = window.setTimeout(() => goResults(answer), AUTO_MS);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [last?.id, last?.status]);

  useEffect(() => {
    if (s.exchanges.length) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [s.exchanges.length, last?.status, editing]);

  useEffect(() => setEditing(null), [last?.id]);

  if (emergency) {
    const answer = s.answer?.next === "emergency" ? s.answer : undefined;
    const placeText = answer?.place?.text ?? profile.location ?? undefined;
    const origin = s.data?.queryContext.location;
    const named = USE_DEMO && placeText ? findDemoLocation(placeText) : undefined;
    return (
      <div className="app-shell">
        <Header />
        <main>
          <EmergencyView
            origin={named ?? (origin ? { latitude: origin.latitude, longitude: origin.longitude } : DEFAULT_ORIGIN)}
            originName={placeText ?? origin?.resolvedName ?? DEFAULT_ORIGIN.name}
            contact={profile.emergencyContact}
            reason={
              answer
                ? { quote: answer.urgency.span?.quote, score: answer.urgency.score, crisis: answer.urgency.crisis, text: answer.text }
                : undefined
            }
            onExit={() => withTransition(() => navigate(-1), "emergency")}
            onNotEmergency={
              answer
                ? () => {
                    withTransition(() => navigate("/", { replace: true }), "emergency");
                    void s.continueUrgent();
                  }
                : undefined
            }
          />
        </main>
      </div>
    );
  }

  const started = s.exchanges.length > 0;
  return (
    <div className="app-shell conversation-shell">
      <Header />
      <main className={`conversation ${started ? "is-started" : ""}`}>
        <h1 className="sr-only">{t.heroTitle}</h1>
        <ol className="trail" aria-live="polite">
          <li className="stop stop--raahi stop--greet">
            <RaahiMark current={!started} mood="happy" />
            <div className="stop-body">
              <p className="raahi-line">{t.askRaahi}</p>
              {!profile.onboardingDone && !started && (
                <p className="stop-aside">
                  {t.askSetupPre} <Link to="/welcome">{t.askSetupLink}</Link>
                  {t.askSetupPost}
                </p>
              )}
            </div>
          </li>
          {s.exchanges.map((exchange, index) => {
            const latest = index === s.exchanges.length - 1;
            return (
              <Fragment key={exchange.id}>
                <li className="stop stop--you">
                  <span className="footstep" aria-hidden="true" />
                  <div className="you-line">
                    {exchange.kind === "said" && exchange.answer ? <SaidText answer={exchange.answer} /> : <p>{exchange.said}</p>}
                  </div>
                </li>
                <li className={`stop stop--raahi ${latest ? "is-latest" : "is-past"}`}>
                  <RaahiMark current={latest} mood={moodFor(exchange)} />
                  <div className="stop-body">
                    <RaahiTurn
                      exchange={exchange}
                      latest={latest}
                      editing={latest ? editing : null}
                      onEdit={setEditing}
                      onPickCare={(id) => void s.pickCare(id)}
                      onPickPlace={(place, label) => void s.pickPlace(place, label)}
                      onGo={goResults}
                      onEmergency={openEmergency}
                    />
                  </div>
                </li>
              </Fragment>
            );
          })}
        </ol>
        <div ref={endRef} className="trail-end" />

        <div className="conversation-composer">
          {mode === "ask" ? (
            <AskRaahi isLoading={s.busy} compact={started} clearOnAsk onAsk={(text) => void submit(text)} />
          ) : (
            <SearchPanel
              initialService=""
              initialLocation={profile.location ?? ""}
              isLoading={s.busy}
              onSearch={(values) =>
                withTransition(
                  () =>
                    navigate(
                      `/results?${new URLSearchParams({
                        care: values.service,
                        place: values.coordinates ? "" : values.location,
                        ...(values.coordinates
                          ? { lat: values.coordinates.latitude.toFixed(5), lon: values.coordinates.longitude.toFixed(5) }
                          : {}),
                      }).toString()}`,
                    ),
                  "to-results",
                )
              }
            />
          )}
          <div className="composer-links">
            <button
              type="button"
              className="link-button"
              onClick={() => withTransition(() => setMode(mode === "ask" ? "pick" : "ask"), "turn")}
            >
              {mode === "ask" ? t.askPickInstead : t.askTypeInstead}
            </button>
            {started && (
              <button type="button" className="link-button" onClick={() => withTransition(s.reset, "turn")}>
                {t.startOver}
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );

  function moodFor(exchange: Exchange) {
    if (exchange.status === "thinking") return "thinking" as const;
    if (exchange.status === "failed") return "concerned" as const;
    const next = exchange.answer?.next;
    if (next === "emergency") return "concerned" as const;
    if (next === "results" && !exchange.answer?.results?.results.length) return "concerned" as const;
    return next === "results" ? ("happy" as const) : ("thinking" as const);
  }
}

/** Raahi standing on the trail. Only the current stop has the full mascot (it carries the shared name). */
function RaahiMark({ current, mood }: { current: boolean; mood: "happy" | "thinking" | "concerned" }) {
  return current ? (
    <span className="raahi-mark is-current" style={{ viewTransitionName: "raahi-guide" } as React.CSSProperties}>
      <Raahi size={58} mood={mood} />
    </span>
  ) : (
    <span className="raahi-mark" aria-hidden="true">
      <span className="trail-pin" />
    </span>
  );
}

function RaahiTurn({
  exchange,
  latest,
  editing,
  onEdit,
  onPickCare,
  onPickPlace,
  onGo,
  onEmergency,
}: {
  exchange: Exchange;
  latest: boolean;
  editing: "care" | "place" | null;
  onEdit: (which: "care" | "place" | null) => void;
  onPickCare: (id: string) => void;
  onPickPlace: (place: { text: string; coordinates?: { latitude: number; longitude: number } }, label: string) => void;
  onGo: (answer: AskResponse) => void;
  onEmergency: () => void;
}) {
  const { t, lang } = useI18n();
  if (exchange.status === "thinking") {
    return (
      <p className="raahi-line is-thinking">
        {t.askReading}
        <span className="dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
      </p>
    );
  }
  if (exchange.status === "failed" || !exchange.answer) return <p className="raahi-line">{t.askFailed}</p>;
  const answer = exchange.answer;
  const care = answer.care ? careName(answer.care.id, lang, answer.care.name) : "";
  const place = answer.place?.text ? placeName(answer.place.text, lang) : t.currentLocation;
  const asking = answer.next === "ask_care" ? "care" : answer.next === "ask_place" ? "place" : null;
  const open = editing ?? (latest ? asking : null);
  const found = answer.results?.results.length ?? 0;

  const line =
    answer.next === "emergency"
      ? t.emergencyLine
      : answer.next === "results"
        ? found
          ? t.foundLine(found, answer.results ? serviceName(answer.results, lang) : care, place)
          : t.foundNone(care, place)
        : asking === "care"
          ? answer.careOptions.length
            ? t.askCareQ
            : t.askCareNone
          : t.askPlaceQ;

  return (
    <>
      {answer.condition && (lang !== "hi" || answer.condition.nameHi) && (
        <p className="stop-aside">
          {t.rowDescribed}: <strong>{lang === "hi" ? answer.condition.nameHi : answer.condition.name}</strong>
        </p>
      )}
      <p className="raahi-line">{line}</p>
      {latest && (answer.care || answer.place) && (
        <Signposts answer={answer} shared={answer.next === "results"} onChange={(which) => onEdit(editing === which ? null : which)} />
      )}
      {latest && open === "care" && (
        <div className="fork">
          {answer.careOptions.length > 0 && !editing ? (
            <ul className="option-list">
              {answer.careOptions.map((option, index) => (
                <li key={option.id} style={{ "--i": index } as React.CSSProperties}>
                  <button type="button" onClick={() => onPickCare(option.id)}>
                    <span>{lang === "hi" ? option.nameHi : option.name}</span>
                    <ArrowRight size={18} aria-hidden="true" />
                  </button>
                </li>
              ))}
              <li>
                <button type="button" className="option-other" onClick={() => onEdit("care")}>
                  {t.askCareOther}
                </button>
              </li>
            </ul>
          ) : (
            <CarePicker onPick={(id) => onPickCare(id)} />
          )}
        </div>
      )}
      {latest && open === "place" && (
        <div className="fork">
          <PlacePicker
            message={
              answer.placeMessage
                ? /outside India/i.test(answer.placeMessage)
                  ? t.outsideIndia
                  : /demo/i.test(answer.placeMessage)
                    ? t.demoPlaceOnly
                    : t.placeNotFound
                : undefined
            }
            suggestions={answer.placeSuggestions}
            onPick={(picked) => onPickPlace(picked, picked.coordinates ? t.currentLocation : picked.text)}
          />
        </div>
      )}
      {latest && answer.next === "results" && (
        <div className={`destination ${found ? "is-found" : "is-empty"}`}>
          <span className="destination-pin" aria-hidden="true">
            <MapPinned size={22} />
          </span>
          <button type="button" className="primary-button destination-go" onClick={() => onGo(answer)}>
            {found ? t.foundGo : t.foundGoNone}
            <ArrowRight size={18} aria-hidden="true" />
            {found > 0 && <i className="destination-timer" aria-hidden="true" />}
          </button>
        </div>
      )}
      {latest && answer.next === "emergency" && (
        <button type="button" className="primary-button destination-emergency" onClick={onEmergency}>
          {t.emCall}
        </button>
      )}
    </>
  );
}
