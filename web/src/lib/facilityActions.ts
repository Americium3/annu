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

/**
 * A number people can read and dial from another phone: Indian 10-digit
 * numbers as "+91 98765 43210"; anything else (toll-free, foreign) as given.
 */
export function displayPhone(phone: string) {
  const digits = phone.replace(/[^\d]/g, "");
  const national = digits.replace(/^(91|0)(?=\d{10}$)/, "");
  if (national.length === 10 && !/^1800/.test(national)) return `+91 ${national.slice(0, 5)} ${national.slice(5)}`;
  if (/^1800\d{6,7}$/.test(national)) return `${national.slice(0, 4)} ${national.slice(4, 7)} ${national.slice(7)}`;
  return phone;
}

export function telUrl(phone: string) {
  return `tel:${phone.replace(/[^\d+]/g, "")}`;
}
