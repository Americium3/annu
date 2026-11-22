import { ArrowLeft, LoaderCircle, LocateFixed, Phone, UserRound } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { demoFacilities } from "../data/demo";
import { useI18n } from "../i18n";
import { telUrl } from "../lib/facilityActions";
import type { EmergencyContact } from "../lib/profile";
import type { FacilityRecommendation } from "../types";
import { FacilityActions } from "./FacilityActions";

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
 * Prototype note: the demo data has no "emergency department" field, so this
 * lists the nearest hospitals (clinics excluded). Production needs a verified
 * emergency-capability flag before this list can claim more than that.
 */
export function EmergencyView({
  origin,
  originName,
  contact,
  onExit,
}: {
  origin: Point;
  originName: string;
  contact: EmergencyContact | null;
  onExit: () => void;
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
  const hospitals = useMemo<FacilityRecommendation[]>(
    () =>
      demoFacilities
        .filter((facility) => !/clinic/i.test(facility.type))
        .map((facility) => ({ ...facility, distanceKm: distanceKm(from, facility) }))
        .sort((a, b) => a.distanceKm - b.distanceKm)
        .slice(0, 5),
    [from],
  );

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

        <a className="call-108" href="tel:108">
          <Phone size={28} aria-hidden="true" />
          <span>
            <strong>{t.emCall}</strong>
            <small>{t.emCallHint}</small>
          </span>
        </a>

        {contact && (
          <a className="call-contact" href={telUrl(`+91${contact.phone}`)}>
            <UserRound size={22} aria-hidden="true" />
            <strong>{t.callContact(contact.name)}</strong>
          </a>
        )}

        <div className="emergency-list-head">
          <h2>{t.emNearest}</h2>
          <p>
            {locating ? (
              <>
                <LoaderCircle className="spin" size={15} aria-hidden="true" /> {t.emLocating}
              </>
            ) : position ? (
              t.emFrom(t.emYourLocation)
            ) : (
              <>
                {t.emFrom(originName)} ·{" "}
                <button type="button" className="link-button" onClick={locate}>
                  <LocateFixed size={15} aria-hidden="true" /> {t.emUseLocation}
                </button>
              </>
            )}
          </p>
        </div>

        <ol className="emergency-list">
          {hospitals.map((facility, index) => (
            <li key={facility.id}>
              <div className="emergency-hospital">
                <h3>{facility.name}</h3>
                <p>{facility.address}</p>
              </div>
              <p className="card-distance">
                <strong>{facility.distanceKm.toFixed(1)}</strong> km
              </p>
              <FacilityActions facility={facility} primary={index === 0} share={false} />
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
