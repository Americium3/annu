import { MessageCircle, Navigation, Phone } from "lucide-react";
import { useI18n } from "../i18n";
import { directionsUrl, telUrl, whatsappUrl } from "../lib/facilityActions";
import type { FacilityRecommendation } from "../types";

/**
 * What people actually do next with a hospital in India: phone it, get there,
 * or send it to family. Links stop click propagation so a card stays put.
 */
export function FacilityActions({
  facility,
  service,
}: {
  facility: FacilityRecommendation;
  service: string;
}) {
  const { t } = useI18n();
  const stop = (event: React.MouseEvent) => event.stopPropagation();
  return (
    <div className="facility-actions">
      {facility.phone ? (
        <a className="action-button" href={telUrl(facility.phone)} onClick={stop}>
          <Phone size={16} aria-hidden="true" />
          {t.call}
        </a>
      ) : (
        <span className="action-missing">
          <Phone size={15} aria-hidden="true" />
          {t.noPhone}
        </span>
      )}
      <a
        className="action-button"
        href={directionsUrl(facility)}
        target="_blank"
        rel="noreferrer"
        onClick={stop}
      >
        <Navigation size={16} aria-hidden="true" />
        {t.directions}
      </a>
      <a
        className="action-button"
        href={whatsappUrl(facility, service)}
        target="_blank"
        rel="noreferrer"
        aria-label={t.shareLabel(facility.name)}
        onClick={stop}
      >
        <MessageCircle size={16} aria-hidden="true" />
        {t.share}
      </a>
    </div>
  );
}
