import { Check, Crosshair, LoaderCircle, LocateFixed, MapPin, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { locations, services } from "../data/demo";
import { useI18n } from "../i18n";
import { resolveLocation, resolveService } from "../lib/demoApi";
import type { LocationOption, ServiceOption } from "../types";

export interface SearchValues {
  service: string;
  location: string;
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

const commonSearches = ["Kidney dialysis", "MRI scan", "Emergency C-section", "NICU"];

function matchesService(service: ServiceOption, query: string) {
  const normalized = query.toLowerCase().trim();
  if (!normalized) return true;
  return (
    service.name.toLowerCase().includes(normalized) ||
    service.synonyms.some((synonym) => synonym.toLowerCase().includes(normalized))
  );
}

export function SearchPanel({
  initialService,
  initialLocation,
  radiusKm,
  isLoading,
  onSearch,
}: SearchPanelProps) {
  const [service, setService] = useState(initialService);
  const [location, setLocation] = useState(initialLocation);
  const [radius, setRadius] = useState(radiusKm);
  const [serviceOpen, setServiceOpen] = useState(false);
  const [locationOpen, setLocationOpen] = useState(false);
  const [geoState, setGeoState] = useState<"idle" | "locating" | "found" | "error">("idle");
  const [coordinates, setCoordinates] = useState<SearchValues["coordinates"]>();
  const serviceRef = useRef<HTMLDivElement>(null);
  const locationRef = useRef<HTMLDivElement>(null);
  const { t } = useI18n();

  useEffect(() => {
    setService(initialService);
    setLocation(initialLocation);
    setRadius(radiusKm);
  }, [initialService, initialLocation, radiusKm]);

  useEffect(() => {
    function closeOnOutsideClick(event: MouseEvent) {
      if (!serviceRef.current?.contains(event.target as Node)) {
        setServiceOpen(false);
      }
      if (!locationRef.current?.contains(event.target as Node)) {
        setLocationOpen(false);
      }
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, []);

  const serviceMatches = services.filter((item) => matchesService(item, service));

  function handleServiceSelect(option: ServiceOption) {
    setService(option.name);
    setServiceOpen(false);
  }

  function handleLocationSelect(option: LocationOption) {
    setLocation(`${option.name}, ${option.region}`);
    setCoordinates(undefined);
    setLocationOpen(false);
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit(service);
  }

  function submit(serviceText: string) {
    const normalizedService = resolveService(serviceText).name;
    const normalizedLocation = resolveLocation(location);
    setService(normalizedService);
    setLocation(`${normalizedLocation.name}, ${normalizedLocation.region}`);
    onSearch({
      service: normalizedService,
      location: `${normalizedLocation.name}, ${normalizedLocation.region}`,
      radiusKm: radius,
      coordinates,
    });
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      setGeoState("error");
      return;
    }

    setGeoState("locating");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const nextCoordinates = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        };
        setCoordinates(nextCoordinates);
        setLocation(t.currentLocation);
        setGeoState("found");
      },
      () => setGeoState("error"),
      { enableHighAccuracy: true, timeout: 8000 },
    );
  }

  return (
    <div className="search-wrap">
      <form className="search-panel" onSubmit={handleSubmit} id="search">
        <div className="search-field search-field-care" ref={serviceRef}>
          <label htmlFor="service-input">{t.careLabel}</label>
          <div className="field-control">
            <Search className="field-icon" size={19} aria-hidden="true" />
            <input
              id="service-input"
              value={service}
              onChange={(event) => {
                setService(event.target.value);
                setServiceOpen(true);
              }}
              onFocus={() => setServiceOpen(true)}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown" && serviceMatches.length > 0) {
                  event.preventDefault();
                  handleServiceSelect(serviceMatches[0]);
                }
                if (event.key === "Escape") setServiceOpen(false);
              }}
              placeholder={t.carePlaceholder}
              autoComplete="off"
              enterKeyHint="next"
              aria-autocomplete="list"
              aria-controls="service-suggestions"
              aria-expanded={serviceOpen}
            />
          </div>
          {serviceOpen && (
            <div className="suggestions" id="service-suggestions" role="listbox">
              <div className="suggestions-heading">{t.suggestionsServices}</div>
              {serviceMatches.length > 0 ? (
                serviceMatches.map((option) => (
                  <button
                    type="button"
                    className="suggestion-item"
                    key={option.id}
                    role="option"
                    aria-selected={service === option.name}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => handleServiceSelect(option)}
                  >
                    <span>
                      <strong>{option.name}</strong>
                      <small>{option.synonyms.slice(0, 2).join(" · ")}</small>
                    </span>
                    {service === option.name && <Check className="suggestion-check" size={16} />}
                  </button>
                ))
              ) : (
                <p className="suggestion-empty">{t.noServiceMatch}</p>
              )}
            </div>
          )}
        </div>

        <div className="search-field search-field-place" ref={locationRef}>
          <label htmlFor="location-input">{t.placeLabel}</label>
          <div className="field-control">
            <MapPin className="field-icon" size={19} aria-hidden="true" />
            <input
              id="location-input"
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
              autoComplete="off"
              enterKeyHint="search"
              aria-autocomplete="list"
              aria-controls="location-suggestions"
              aria-expanded={locationOpen}
            />
            <button
              className={`locate-button ${geoState === "found" ? "is-found" : ""}`}
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
          </div>
          {geoState === "error" && <p className="field-message">{t.locationError}</p>}
          {locationOpen && (
            <div className="suggestions" id="location-suggestions" role="listbox">
              <div className="suggestions-heading">
                <span>{t.suggestionsPlaces}</span>
                <button type="button" onClick={useCurrentLocation}>
                  <LocateFixed size={14} /> {t.useLocation}
                </button>
              </div>
              {locations
                .filter((option) =>
                  `${option.name} ${option.region}`.toLowerCase().includes(location.toLowerCase()),
                )
                .map((option) => (
                  <button
                    type="button"
                    className="suggestion-item"
                    key={option.id}
                    role="option"
                    aria-selected={location.includes(option.name)}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => handleLocationSelect(option)}
                  >
                    <span>
                      <strong>{option.name}</strong>
                      <small>{option.region}</small>
                    </span>
                  </button>
                ))}
            </div>
          )}
        </div>

        <div className="search-field search-field-radius">
          <label htmlFor="radius-select">{t.distanceLabel}</label>
          <select
            id="radius-select"
            value={radius}
            onChange={(event) => setRadius(Number(event.target.value))}
          >
            {[5, 10, 20, 50].map((km) => (
              <option key={km} value={km}>
                {t.within(km)}
              </option>
            ))}
          </select>
        </div>

        <button className="primary-button search-submit" type="submit" disabled={isLoading}>
          {isLoading ? <LoaderCircle className="spin" size={18} /> : <Search size={18} />}
          {isLoading ? t.finding : t.find}
        </button>
      </form>

      <p className="common-searches">
        <span>{t.commonSearches}</span>
        {commonSearches.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => {
              setService(name);
              submit(name);
            }}
          >
            {name}
          </button>
        ))}
      </p>
    </div>
  );
}
