import { AlertTriangle, CheckCircle2, HelpCircle } from "lucide-react";
import { useI18n } from "../i18n";
import type { ConfidenceLevel } from "../types";

/** Confidence as an icon and words in the status colour: never a coloured pill. */
export function ConfidenceBadge({ level }: { level: ConfidenceLevel }) {
  const { t } = useI18n();
  const Icon = level === "high" ? CheckCircle2 : level === "medium" ? HelpCircle : AlertTriangle;
  const label =
    level === "high" ? t.confidenceHigh : level === "medium" ? t.confidenceMedium : t.confidenceLow;
  return (
    <span className={`confidence confidence-${level}`}>
      <Icon size={15} aria-hidden="true" />
      {label}
    </span>
  );
}
