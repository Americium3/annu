import { ArrowRight, Check, ChevronDown, Crosshair, LoaderCircle, LocateFixed } from "lucide-react";
import { Fragment, useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { fetchLocations, fetchServices } from "../lib/api";
import { RADIUS_OPTIONS } from "../lib/profile";
import type { LocationOption, ServiceOption } from "../types";

export interface SearchValues {
  service: string;
  location: string;
  /** Distance cap in km; 0 = any distance (the recommender decides). */
  radiusKm: number;
  coordinates?: {
    latitude: number;
    longitude: number;
  };
}

interface SearchPanelProps {
  initialService: string;
  initialLocation: string;
  radiusKm: number;
  isLoading: boolean;
  onSearch: (values: SearchValues) => void;
}

function matchesService(service: ServiceOption, query: string) {
  const normalized = query.toLowerCase().trim();
  if (!normalized) return true;
  return (
    service.name.toLowerCase().includes(normalized) ||
    service.synonyms.some((synonym) => synonym.toLowerCase().includes(normalized))
  );
}

/**
 * Search as one sentence with blanks: "I need [care] near [place] [within
 * 10 km]." It reads the way people describe what they need, the blanks are
 * big enough to tap, and each language orders the blanks its own way (the
 * template lives in i18n). Every blank is a real labelled input.
 */
export function SearchPanel({ initialService, initialLocation, radiusKm, isLoading, onSearch }: SearchPanelProps) {
  const { t } = useI18n();
  const [service, setService] = useState(initialService);
  const [location, setLocation] = useState(initialLocation);
  const [radius, setRadius] = useState(radiusKm);
  const [serviceOpen, setServiceOpen] = useState(false);
  const [locationOpen, setLocationOpen] = useState(false);
  const [geoState, setGeoState] = useState<"idle" | "locating" | "found" | "error">("idle");
  const [coordinates, setCoordinates] = useState<SearchValues["coordinates"]>();
  const [services, setServices] = useState<ServiceOption[]>([]);
  const [locationOptions, setLocationOptions] = useState<LocationOption[]>([]);
  const serviceRef = useRef<HTMLSpanElement>(null);
  const locationRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    setService(initialService);
    setLocation(initialLocation);
    setRadius(radiusKm);
  }, [initialService, initialLocation, radiusKm]);

  useEffect(() => {
    function closeOnOutsideClick(event: MouseEvent) {
      if (!serviceRef.current?.contains(event.target as Node)) setServiceOpen(false);
      if (!locationRef.current?.contains(event.target as Node)) setLocationOpen(false);
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, []);

  useEffect(() => {
    fetchServices()
      .then(setServices)
      .catch(() => setServices([]));
  }, []);

  useEffect(() => {
    if (!locationOpen || coordinates) return;
    const handle = window.setTimeout(() => {
      fetchLocations(location)
        .then(setLocationOptions)
        .catch(() => setLocationOptions([]));
    }, 180);
    return () => window.clearTimeout(handle);
  }, [location, locationOpen, coordinates]);

  const serviceMatches = services.filter((item) => matchesService(item, service)).slice(0, 8);

  function submit(serviceText = service, radiusValue = radius) {
    onSearch({ service: serviceText.trim(), location: location.trim(), radiusKm: radiusValue, coordinates });
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      setGeoState("error");
      return;
    }
    setGeoState("locating");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setCoordinates({ latitude: position.coords.latitude, longitude: position.coords.longitude });
        setLocation(t.currentLocation);
        setGeoState("found");
        setLocationOpen(false);
      },
      () => setGeoState("error"),
      { enableHighAccuracy: true, timeout: 8000 },
    );
  }

  // Each blank is exactly as wide as its text: an invisible copy of the text
  // sits in the same grid cell and sets the width, in every browser.
  const sizer = (value: string, placeholder: string, input: React.ReactNode) => (
    <span className="blank-sizer" data-value={`${value || placeholder} `}>
      {input}
    </span>
  );

  const slots: Record<string, React.ReactNode> = {
    "{service}": (
      <span className="blank" ref={serviceRef}>
        {sizer(
          service,
          t.carePlaceholder,
        <input
          id="service-input"
          className="blank-input"
          size={1}
          value={service}
          onChange={(event) => {
            setService(event.target.value);
            setServiceOpen(true);
          }}
          onFocus={() => setServiceOpen(true)}
          onKeyDown={(event) => {
            if (event.key === "Escape") setServiceOpen(false);
          }}
          placeholder={t.carePlaceholder}
          aria-label={t.careLabel}
          autoComplete="off"
          enterKeyHint="next"
          aria-autocomplete="list"
          aria-controls="service-suggestions"
          aria-expanded={serviceOpen}
        />,
        )}
        {serviceOpen && (
          <span className="suggestions" id="service-suggestions" role="listbox">
            <span className="suggestions-heading">{t.suggestionsServices}</span>
            {serviceMatches.length > 0 ? (
              serviceMatches.map((option) => (
                <button
                  type="button"
                  className="suggestion-item"
                  key={option.id}
                  role="option"
                  aria-selected={service === option.name}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => {
                    setService(option.name);
                    setServiceOpen(false);
                  }}
                >
                  <span>
                    <strong>{option.name}</strong>
                    <small>{option.synonyms.slice(0, 2).join(" · ") || option.category}</small>
                  </span>
                  {service === option.name && <Check className="suggestion-check" size={16} />}
                </button>
              ))
            ) : (
              <span className="suggestion-empty">{t.noServiceMatch}</span>
            )}
          </span>
        )}
      </span>
    ),
    "{place}": (
      <span className="blank" ref={locationRef}>
        {sizer(
          location,
          t.placePlaceholder,
        <input
          id="location-input"
          className="blank-input"
          size={1}
          value={location}
          onChange={(event) => {
            setLocation(event.target.value);
            setCoordinates(undefined);
            setGeoState("idle");
            setLocationOpen(true);
          }}
          onFocus={() => setLocationOpen(true)}
          onKeyDown={(event) => {
            if (event.key === "Escape") setLocationOpen(false);
          }}
          placeholder={t.placePlaceholder}
          aria-label={t.placeLabel}
          autoComplete="off"
          enterKeyHint="search"
          aria-autocomplete="list"
          aria-controls="location-suggestions"
          aria-expanded={locationOpen}
        />,
        )}
        <button
          className={`blank-locate ${geoState === "found" ? "is-found" : ""}`}
          type="button"
          onClick={useCurrentLocation}
          aria-label={t.useLocation}
          title={t.useLocation}
        >
          {geoState === "locating" ? (
            <LoaderCircle className="spin" size={18} />
          ) : geoState === "found" ? (
            <Check size={18} />
          ) : (
            <Crosshair size={18} />
          )}
        </button>
        {locationOpen && (
          <span className="suggestions" id="location-suggestions" role="listbox">
            <span className="suggestions-heading">
              <span>{t.suggestionsPlaces}</span>
              <button type="button" onClick={useCurrentLocation}>
                <LocateFixed size={14} /> {t.useLocation}
              </button>
            </span>
            {locationOptions.length === 0 && <span className="suggestion-empty">{t.placeEmpty}</span>}
            {locationOptions.map((option) => (
              <button
                type="button"
                className="suggestion-item"
                key={option.id}
                role="option"
                aria-selected={location.includes(option.name)}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  setLocation(`${option.name}, ${option.region}`);
                  setCoordinates(undefined);
                  setLocationOpen(false);
                }}
              >
                <span>
                  <strong>{option.name}</strong>
                  <small>
                    {option.kind ? `${option.kind} · ` : ""}
                    {option.region}
                  </small>
                </span>
              </button>
            ))}
          </span>
        )}
      </span>
    ),
    "{distance}": (
      <span className="blank blank-select">
        <select
          id="radius-select"
          className="blank-input"
          value={radius}
          aria-label={t.distanceLabel}
          onChange={(event) => setRadius(Number(event.target.value))}
        >
          {RADIUS_OPTIONS.map((km) => (
            <option key={km} value={km}>
              {km === 0 ? t.distanceAny : t.distanceWithin(km)}
            </option>
          ))}
        </select>
        <ChevronDown className="blank-chevron" size={22} aria-hidden="true" />
      </span>
    ),
  };

  return (
    <div className="search-wrap">
      <form
        className="sentence"
        role="search"
        id="search"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <p className="sentence-line">
          {t.searchTemplate.map((part, index) => {
            const nextPart = t.searchTemplate[index + 1];
            const space = nextPart && !/^[.।,!?]/.test(nextPart) ? " " : "";
            return (
              <Fragment key={index}>
                {slots[part] ?? <span className="sentence-word">{part}</span>}
                {space}
              </Fragment>
            );
          })}
        </p>
        {geoState === "error" && <p className="field-message">{t.locationError}</p>}
        <div className="sentence-actions">
          <button className="primary-button search-submit" type="submit" disabled={isLoading}>
            {isLoading ? t.finding : t.find}
            {isLoading ? <LoaderCircle className="spin" size={20} /> : <ArrowRight size={20} />}
          </button>
        </div>
      </form>
    </div>
  );
}
