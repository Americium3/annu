import { AlertTriangle, CheckCircle2, HelpCircle } from "lucide-react";
import type { ConfidenceLevel } from "../types";

export function ConfidenceBadge({
  level,
  compact = false,
}: {
  level: ConfidenceLevel;
  compact?: boolean;
}) {
  const Icon = level === "high" ? CheckCircle2 : level === "medium" ? HelpCircle : AlertTriangle;
  return (
    <span className={`confidence-badge confidence-${level} ${compact ? "is-compact" : ""}`}>
      <Icon size={13} aria-hidden="true" />
      {level === "high" ? "High confidence" : level === "medium" ? "Medium confidence" : "Low confidence"}
    </span>
  );
}
