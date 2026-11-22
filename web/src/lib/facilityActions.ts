import type { FacilityRecommendation } from "../types";

/** Google Maps directions to the facility's confirmed coordinates. */
export function directionsUrl(facility: FacilityRecommendation) {
  return `https://www.google.com/maps/dir/?api=1&destination=${facility.latitude},${facility.longitude}`;
}

/**
 * WhatsApp share link. Families decide together, and WhatsApp is how a result
 * reaches the relative who will make the call or the trip.
 */
export function whatsappUrl(facility: FacilityRecommendation, service: string) {
  const lines = [
    facility.name,
    `${facility.address}, ${facility.district}, ${facility.state} ${facility.pincode}`,
    `${service}: ${facility.recommendationSummary}`,
    facility.phone ? `Phone: ${facility.phone}` : "",
    `Map: ${directionsUrl(facility)}`,
  ].filter(Boolean);
  return `https://wa.me/?text=${encodeURIComponent(lines.join("\n"))}`;
}

export function telUrl(phone: string) {
  return `tel:${phone.replace(/[^\d+]/g, "")}`;
}
