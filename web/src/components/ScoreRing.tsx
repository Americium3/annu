import { useI18n } from "../i18n";

/** The match score as a plain number with its scale, tinted by band. */
export function ScoreRing({ score, size = "small" }: { score: number; size?: "small" | "large" }) {
  const { t } = useI18n();
  const band = score >= 70 ? "strong" : score >= 45 ? "mid" : "low";
  return (
    <div
      className={`match-score match-${band} ${size === "large" ? "match-score-large" : ""}`}
      role="img"
      aria-label={t.scoreAria(score)}
    >
      <strong>{score}</strong>
      <span>
        /100 <br />
        {t.matchScore}
      </span>
    </div>
  );
}
