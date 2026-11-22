import { Check, Crosshair, LoaderCircle, LocateFixed, MapPin, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { fetchLocations, fetchServices } from "../lib/api";
import type { LocationOption, ServiceOption } from "../types";

export interface SearchValues {
  service: string;
  location: string;
  coordinates?: {
    latitude: number;
    longitude: number;
  };
}

interface SearchPanelProps {
  initialService: string;
  initialLocation: string;
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
  isLoading,
  onSearch,
}: SearchPanelProps) {
  const [service, setService] = useState(initialService);
  const [location, setLocation] = useState(initialLocation);
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
  }, [initialService, initialLocation]);

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

  const [services, setServices] = useState<ServiceOption[]>([]);
  const [locationOptions, setLocationOptions] = useState<LocationOption[]>([]);

  // Service catalogue from the backend, loaded once.
  useEffect(() => {
    fetchServices()
      .then(setServices)
      .catch(() => setServices([]));
  }, []);

  // Place suggestions (districts, cities, PIN codes) from the backend, debounced.
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
    // The backend resolves free text (service → tag, place → district / city / PIN / coordinates)
    // and chooses the radius itself, widening until it finds a facility with evidence.
    onSearch({
      service: serviceText.trim(),
      location: location.trim(),
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
                      <small>{option.synonyms.slice(0, 2).join(" · ") || option.category}</small>
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
              {locationOptions.length === 0 && <p className="suggestion-empty">{t.placeEmpty}</p>}
              {locationOptions.map((option) => (
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
                    <small>
                      {option.kind ? `${option.kind} · ` : ""}
                      {option.region}
                    </small>
                  </span>
                </button>
              ))}
            </div>
          )}
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
