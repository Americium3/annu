interface ScoreRingProps {
  score: number;
  size?: "small" | "large";
}

export function ScoreRing({ score, size = "small" }: ScoreRingProps) {
  return (
    <div
      className={`score-ring ${size === "large" ? "score-ring-large" : ""}`}
      style={{ "--score": `${score * 3.6}deg` } as React.CSSProperties}
      aria-label={`Recommendation score ${score} out of 100`}
    >
      <span>{score}</span>
      <small>/100</small>
    </div>
  );
}
