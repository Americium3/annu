import { MessageCircle, Navigation, Phone } from "lucide-react";
import { useI18n } from "../i18n";
import { directionsUrl, telUrl, whatsappUrl } from "../lib/facilityActions";
import type { FacilityRecommendation } from "../types";

/**
 * The next step, in the order people need it: get there, phone ahead, tell
 * family. `primary` fills the Directions button for the top choice so the eye
 * lands on one action. Links stop propagation so a tap never also selects
 * the card.
 */
export function FacilityActions({
  facility,
  service,
  primary = false,
  share = true,
  compact = false,
}: {
  facility: FacilityRecommendation;
  service?: string;
  primary?: boolean;
  share?: boolean;
  /** Icon-only buttons for dense board rows (labels stay for screen readers). */
  compact?: boolean;
}) {
  const { t } = useI18n();
  const stop = (event: React.MouseEvent) => event.stopPropagation();
  return (
    <div className={`facility-actions ${compact ? "is-compact" : ""}`}>
      <a
        className={`action-button ${primary ? "action-primary" : ""}`}
        href={directionsUrl(facility)}
        target="_blank"
        rel="noreferrer"
        onClick={stop}
      >
        <Navigation size={17} aria-hidden="true" />
        <span className="action-label">{t.directions}</span>
      </a>
      {facility.phone ? (
        <a className="action-button" href={telUrl(facility.phone)} onClick={stop}>
          <Phone size={17} aria-hidden="true" />
          <span className="action-label">{t.call}</span>
        </a>
      ) : null /* no number: no button, and no line saying so */}
      {share && (
        <a
          className="action-button action-icon"
          href={whatsappUrl(facility, service ?? "")}
          target="_blank"
          rel="noreferrer"
          aria-label={t.shareLabel(facility.name)}
          title={t.shareLabel(facility.name)}
          onClick={stop}
        >
          <MessageCircle size={17} aria-hidden="true" />
          <span className="action-icon-label">{t.share}</span>
        </a>
      )}
    </div>
  );
}
