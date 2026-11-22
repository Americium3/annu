import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { careTerm } from "../data/careTerms";
import { useI18n } from "../i18n";
import type { AskResponse, RecommendationResponse } from "../types";
import { ApiError, ask, getRecommendations, USE_DEMO, type SearchInput } from "./api";
import { withTransition } from "./motion";
import { useProfile } from "./profile";
import { understand } from "./understand";

export type Coordinates = { latitude: number; longitude: number };

/** One step of the conversation: what the person said (or picked), and Raahi's reading of it. */
export interface Exchange {
  id: number;
  said: string;
  kind: "said" | "picked";
  status: "thinking" | "waiting" | "done" | "failed";
  answer?: AskResponse;
  error?: string;
}

interface Session {
  exchanges: Exchange[];
  /** Raahi's latest reading: what care, where, how urgent, and what happens next. */
  answer?: AskResponse;
  data?: RecommendationResponse;
  coords?: Coordinates;
  busy: boolean;
  judging: boolean;
  ask: (text: string) => Promise<AskResponse | undefined>;
  pickCare: (id: string) => Promise<void>;
  pickPlace: (place: { text: string; coordinates?: Coordinates }, label: string) => Promise<void>;
  /** The results page opened from a link: search directly. */
  load: (input: SearchInput, careId: string, placeText: string) => Promise<void>;
  /** From the emergency screen, "not an emergency": continue as an urgent request. */
  continueUrgent: () => Promise<void>;
  reset: () => void;
}

const SessionContext = createContext<Session | null>(null);

export function useSearchSession(): Session {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSearchSession outside SessionProvider");
  return value;
}

/** The search parameters behind an answer, as the results page URL carries them. */
export function resultsUrl(answer: AskResponse, coords?: Coordinates) {
  const params = new URLSearchParams();
  if (answer.care) params.set("care", answer.care.id);
  if (answer.place?.text) params.set("place", answer.place.text);
  if (coords) {
    params.set("lat", coords.latitude.toFixed(5));
    params.set("lon", coords.longitude.toFixed(5));
  }
  params.set("urgency", String(answer.urgency.level));
  return `/results?${params.toString()}`;
}

function careRef(id: string) {
  const term = careTerm(id);
  return { id, name: term?.en ?? id, nameHi: term?.hi ?? id };
}

/**
 * The conversation and its results, shared by the conversation page (/) and
 * the results page (/results), so Back returns to the same conversation and
 * the results page opens instantly after a match.
 */
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const profile = useProfile();
  const { lang } = useI18n();
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [data, setData] = useState<RecommendationResponse>();
  const [coords, setCoords] = useState<Coordinates>();
  const [busy, setBusy] = useState(false);
  const [judging, setJudging] = useState(false);
  const nextId = useRef(1);
  const judgeSeq = useRef(0);
  const answer = [...exchanges].reverse().find((e) => e.answer)?.answer;

  const add = useCallback((said: string, kind: Exchange["kind"]) => {
    const id = nextId.current++;
    withTransition(() => setExchanges((all) => [...all, { id, said, kind, status: "thinking" }]), "turn");
    return id;
  }, []);

  /** The server is still loading its data: Raahi says so and keeps the turn open (no transition, no "done"). */
  const waiting = useCallback((id: number) => {
    setExchanges((all) => all.map((e) => (e.id === id && e.status === "thinking" ? { ...e, status: "waiting" } : e)));
  }, []);

  const settle = useCallback((id: number, patch: Partial<Exchange>) => {
    withTransition(
      () => setExchanges((all) => all.map((e) => (e.id === id ? { ...e, status: "done", ...patch } : e))),
      "turn",
    );
  }, []);

  /** Second pass: the language model reads the top hospitals' own records, then the rows glide into place. */
  const judge = useCallback((input: SearchInput, response?: RecommendationResponse) => {
    const seq = ++judgeSeq.current;
    setJudging(false);
    const meta = response?.metadata.judge;
    if (USE_DEMO || !response?.results.length || !meta?.available || meta.used) return;
    setJudging(true);
    getRecommendations({ ...input, judge: true })
      .then((judged) => {
        if (seq === judgeSeq.current) withTransition(() => setData(judged), "reorder");
      })
      .catch(() => undefined)
      .finally(() => {
        if (seq === judgeSeq.current) setJudging(false);
      });
  }, []);

  /** Search once care and place are known; the result becomes Raahi's answer for exchange `id`. */
  const search = useCallback(
    async (id: number, current: AskResponse, at?: Coordinates) => {
      if (!current.care) return settle(id, { answer: { ...current, next: "ask_care" } });
      if (!current.place?.text && !at) return settle(id, { answer: { ...current, next: "ask_place" } });
      const input: SearchInput = {
        serviceText: current.care.id,
        locationText: current.place?.text ?? "",
        coordinates: at,
        urgency: current.urgency.level,
      };
      judge({ serviceText: "", locationText: "" }); // cancel a pending second pass
      try {
        const results = await getRecommendations(input, () => waiting(id));
        setData(results);
        settle(id, { answer: { ...current, next: "results", results } });
        judge(input, results);
      } catch (caught) {
        const failure = caught instanceof ApiError ? caught : new ApiError(String(caught));
        if (failure.field === "location") {
          settle(id, {
            answer: { ...current, next: "ask_place", placeMessage: failure.message, placeSuggestions: failure.suggestions },
          });
        } else if (failure.field === "service") {
          settle(id, { answer: { ...current, care: null, next: "ask_care", careMessage: failure.message } });
        } else settle(id, { status: "failed", error: failure.message });
      }
    },
    [judge, settle, waiting],
  );

  const askRaahi = useCallback(
    async (text: string) => {
      const id = add(text, "said");
      setBusy(true);
      judge({ serviceText: "", locationText: "" });
      try {
        const response = await ask({ text, locationText: profile.location ?? "" }, () => waiting(id));
        setCoords(undefined);
        if (response.results) {
          setData(response.results);
          if (response.care) {
            judge(
              {
                serviceText: response.care.id,
                locationText: response.place?.text ?? profile.location ?? "",
                urgency: response.urgency.level,
              },
              response.results,
            );
          }
        }
        settle(id, { answer: response });
        return response;
      } catch (caught) {
        settle(id, { status: "failed", error: caught instanceof Error ? caught.message : String(caught) });
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [add, judge, profile.location, settle, waiting],
  );

  const pickCare = useCallback(
    async (careId: string) => {
      if (!answer) return;
      const ref = careRef(careId);
      const id = add(lang === "hi" ? ref.nameHi : ref.name, "picked");
      setBusy(true);
      await search(id, { ...answer, care: { ...ref, source: "picked" }, careOptions: [], careOptionsSpan: undefined }, coords);
      setBusy(false);
    },
    [add, answer, coords, lang, search],
  );

  const pickPlace = useCallback(
    async (place: { text: string; coordinates?: Coordinates }, label: string) => {
      if (!answer) return;
      const id = add(label, "picked");
      setBusy(true);
      setCoords(place.coordinates);
      await search(
        id,
        {
          ...answer,
          place: { text: place.text || null, here: Boolean(place.coordinates), source: "picked" },
          placeMessage: undefined,
          placeSuggestions: undefined,
        },
        place.coordinates,
      );
      setBusy(false);
    },
    [add, answer, search],
  );

  const load = useCallback(
    async (input: SearchInput, careId: string, placeText: string) => {
      setBusy(true);
      try {
        const results = await getRecommendations(input);
        setData(results);
        setCoords(input.coordinates);
        if (!answer) {
          // Opened from a link: give the summary bar something to show.
          setExchanges([
            {
              id: nextId.current++,
              said: "",
              kind: "picked",
              status: "done",
              answer: {
                text: "",
                method: "rules",
                llm: { used: false },
                urgency: {
                  level: (input.urgency ?? 4) as 1 | 2 | 3 | 4,
                  score: { 1: 100, 2: 85, 3: 60, 4: 15 }[(input.urgency ?? 4) as 1 | 2 | 3 | 4],
                  label: "",
                  rule: null,
                  source: "none",
                  crisis: false,
                  emergency: false,
                },
                care: { ...careRef(careId), source: "picked" },
                careOptions: [],
                place: { text: placeText || null, here: Boolean(input.coordinates), source: "picked" },
                next: "results",
                results,
              },
            },
          ]);
        }
        judge(input, results);
      } finally {
        setBusy(false);
      }
    },
    [answer, judge],
  );

  const continueUrgent = useCallback(async () => {
    const said = answer?.text ?? exchanges[exchanges.length - 1]?.said ?? "";
    const local = understand(said, () => false, { readPastEmergency: true });
    const urgent: AskResponse = {
      ...local,
      urgency: { ...local.urgency, level: 3, score: 60, emergency: false, label: "urgent" },
      care: local.care ?? (local.careOptions.length ? null : { ...careRef("emergency-24x7"), source: "rules" }),
      place: local.place ?? (profile.location ? { text: profile.location, here: false, source: "saved" } : null),
      next: "results",
    };
    const id = add(said, "said");
    setBusy(true);
    await search(id, urgent);
    setBusy(false);
  }, [add, answer, exchanges, profile.location, search]);

  const reset = useCallback(() => {
    judgeSeq.current += 1;
    setJudging(false);
    setExchanges([]);
    setData(undefined);
    setCoords(undefined);
  }, []);

  const value = useMemo<Session>(
    () => ({
      exchanges,
      answer,
      data,
      coords,
      busy,
      judging,
      ask: askRaahi,
      pickCare,
      pickPlace,
      load,
      continueUrgent,
      reset,
    }),
    [answer, askRaahi, busy, continueUrgent, coords, data, exchanges, judging, load, pickCare, pickPlace, reset],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
