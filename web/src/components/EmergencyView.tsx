import { ArrowLeft, ArrowRight, HeartHandshake, LoaderCircle, LocateFixed, Phone, UserRound } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { demoFacilities } from "../data/demo";
import { useI18n } from "../i18n";
import { getRecommendations, USE_DEMO } from "../lib/api";
import { telUrl } from "../lib/facilityActions";
import type { EmergencyContact } from "../lib/profile";
import type { FacilityRecommendation } from "../types";
import { FacilityActions } from "./FacilityActions";
import { RaahiSays } from "./Raahi";
import { UrgencyMeter } from "./Understood";

/** Why the emergency screen opened: the words that set it off and the emergency score (80+). */
export interface EmergencyReason {
  quote?: string;
  score?: number;
  crisis?: boolean;
  placeText?: string;
  text?: string;
}

interface Point {
  latitude: number;
  longitude: number;
}

function distanceKm(a: Point, b: Point) {
  const rad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = rad(b.latitude - a.latitude);
  const dLon = rad(b.longitude - a.longitude);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude)) * Math.sin(dLon / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(h));
}

/**
 * Emergency: nothing to read. Calling 108 comes first and is the biggest thing
 * on the screen; below it, the nearest hospitals by straight-line distance,
 * each with Directions and Call. No scores, no evidence, no filters.
 *
 * Live data: the list asks the recommender for "emergency" near the person
 * and shows the closest five of what it returns. Demo data has no emergency
 * field, so demo mode lists the nearest hospitals (clinics excluded). If the
 * list can't load, the screen still has Call 108 and the saved contact.
 */
export function EmergencyView({
  origin,
  originName,
  contact,
  reason,
  onExit,
  onNotEmergency,
}: {
  origin: Point;
  originName: string;
  contact: EmergencyContact | null;
  reason?: EmergencyReason;
  onExit: () => void;
  onNotEmergency?: () => void;
}) {
  const { t } = useI18n();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [position, setPosition] = useState<Point>();
  const [locating, setLocating] = useState(false);

  function locate() {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (result) => {
        setPosition({ latitude: result.coords.latitude, longitude: result.coords.longitude });
        setLocating(false);
      },
      () => setLocating(false),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
    );
  }

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
    headingRef.current?.focus();
    // Ask once on entry; the list is already usable while the browser asks.
    locate();
  }, []);

  const from = position ?? origin;
  const [live, setLive] = useState<FacilityRecommendation[] | null>(null);
  const [liveFailed, setLiveFailed] = useState(false);

  useEffect(() => {
    if (USE_DEMO) return;
    let cancelled = false;
    setLiveFailed(false);
    getRecommendations({ serviceText: "emergency-24x7", locationText: originName, coordinates: position, urgency: 2 })
      .then((response) => {
        if (!cancelled) setLive(response.results);
      })
      .catch(() => {
        if (!cancelled) setLiveFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [originName, position]);

  const hospitals = useMemo<FacilityRecommendation[]>(() => {
    const pool = USE_DEMO ? demoFacilities.filter((facility) => !/clinic/i.test(facility.type)) : (live ?? []);
    // Live results already carry distances from the place searched; re-measure only from a device location.
    return pool
      .map((facility) => ({
        ...facility,
        distanceKm: USE_DEMO || position ? distanceKm(from, facility) : facility.distanceKm,
      }))
      .sort((a, b) => a.distanceKm - b.distanceKm)
      .slice(0, 5);
  }, [from, live, position]);

  return (
    <section className="emergency" aria-labelledby="emergency-title">
      <div className="emergency-inner">
        <button className="back-button" type="button" onClick={onExit}>
          <ArrowLeft size={18} aria-hidden="true" />
          {t.emBack}
        </button>

        <h1 id="emergency-title" className="sr-only" tabIndex={-1} ref={headingRef}>
          {t.emergencyDoorTitle}
        </h1>

        {reason?.quote && (
          <div className="emergency-why">
            <RaahiSays mood="concerned" size={52}>
              <strong>{t.emWhy(reason.quote)}</strong>
            </RaahiSays>
            {reason.score !== undefined && <UrgencyMeter score={reason.score} level={reason.score >= 100 ? 1 : 2} compact />}
          </div>
        )}

        <a className="call-108" href="tel:108">
          <Phone size={28} aria-hidden="true" />
          <span>
            <strong>{t.emCall}</strong>
          </span>
        </a>

        {reason?.crisis && (
          <a className="call-contact call-crisis" href="tel:14416">
            <HeartHandshake size={22} aria-hidden="true" />
            <span>
              <strong>
                {t.emCrisis} {t.emCrisisNumber}
              </strong>
              <small>{t.emCrisisNote}</small>
            </span>
          </a>
        )}

        {contact && (
          <a className="call-contact" href={telUrl(`+91${contact.phone}`)}>
            <UserRound size={22} aria-hidden="true" />
            <strong>{t.callContact(contact.name)}</strong>
          </a>
        )}

        <div className="emergency-list-head">
          <h2>{t.emNearest}</h2>
          {locating ? (
            <LoaderCircle className="spin emergency-locating" size={20} aria-label={t.emLocating} />
          ) : (
            !position && (
              <button type="button" className="icon-button" onClick={locate} aria-label={t.emUseLocation} title={t.emUseLocation}>
                <LocateFixed size={18} />
              </button>
            )
          )}
        </div>

        {liveFailed && <p className="emergency-failed">{t.emListFailed}</p>}

        <ol className="emergency-list">
          {hospitals.map((facility, index) => (
            <li key={facility.id} style={{ "--i": index } as React.CSSProperties}>
              <div className="emergency-hospital">
                <h3>{facility.name}</h3>
              </div>
              <p className="card-distance">
                <strong>{facility.distanceKm.toFixed(1)}</strong> km
              </p>
              <FacilityActions facility={facility} primary={index === 0} share={false} />
            </li>
          ))}
        </ol>

        {onNotEmergency && (
          <button type="button" className="link-button emergency-not" onClick={onNotEmergency}>
            {t.emNotEmergency}
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        )}
      </div>
    </section>
  );
}
