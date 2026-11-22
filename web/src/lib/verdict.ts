import type { JudgeVerdict } from "../types";

type Copy = Record<
  "verdictOffers" | "verdictLikely" | "verdictMentions" | "verdictEquipment" | "verdictNot",
  string
>;

/** The judge's verdict in plain words, in the page language. */
export function verdictLabel(t: Copy, verdict: JudgeVerdict): string {
  return {
    offers: t.verdictOffers,
    likely: t.verdictLikely,
    mentions_only: t.verdictMentions,
    equipment_only: t.verdictEquipment,
    not_supported: t.verdictNot,
  }[verdict];
}

/** Verdicts worth a warning line on the card (the others need no words: "doing more by doing less"). */
export function verdictWarns(verdict: JudgeVerdict | null | undefined): boolean {
  return verdict === "mentions_only" || verdict === "equipment_only" || verdict === "not_supported";
}
