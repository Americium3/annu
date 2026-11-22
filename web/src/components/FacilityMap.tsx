import L from "leaflet";
import { useEffect, useMemo } from "react";
import {
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import { ArrowRight, Crosshair } from "lucide-react";
import { useI18n } from "../i18n";
import { scoreBand } from "./FacilityCard";
import { RAAHI_MARK_HTML } from "./Raahi";
import type { FacilityRecommendation, QueryContext } from "../types";

interface FacilityMapProps {
  facilities: FacilityRecommendation[];
  selectedId?: string;
  queryContext?: QueryContext;
  onSelect: (id: string) => void;
  onOpen: (id: string) => void;
  onClearSelection: () => void;
}

function createMarkerIcon(facility: FacilityRecommendation, selected: boolean) {
  // Same pin shape as the rank marker on each card; the tip sits on the location.
  return L.divIcon({
    className: "custom-marker-wrapper",
    html: `<div class="rank-pin rank-pin-${scoreBand(facility.totalScore)} ${selected ? "is-selected" : ""}"><span>${facility.rank}</span></div>`,
    iconSize: [32, 42],
    iconAnchor: [16, 40],
    popupAnchor: [0, -38],
  });
}

// Raahi stands on the search area, so "you are here" is the same face as the brand.
const searchAreaIcon = L.divIcon({
  className: "search-area-marker",
  html: RAAHI_MARK_HTML,
  iconSize: [30, 34],
  iconAnchor: [15, 34],
});

function MapViewport({
  facilities,
  selectedId,
  center,
}: {
  facilities: FacilityRecommendation[];
  selectedId?: string;
  center: [number, number];
}) {
  const map = useMap();

  useEffect(() => {
    if (selectedId) {
      const selected = facilities.find((facility) => facility.id === selectedId);
      if (selected) {
        map.flyTo([selected.latitude, selected.longitude], 13.6, {
          duration: 0.7,
        });
      }
      return;
    }

    if (facilities.length > 1) {
      const bounds = L.latLngBounds(
        facilities.map((facility) => [facility.latitude, facility.longitude]),
      );
      bounds.extend(center);
      map.fitBounds(bounds.pad(0.22), {
        animate: false,
      });
    } else {
      map.setView(center, 13);
    }
  }, [center, facilities, map, selectedId]);

  return null;
}

export function FacilityMap({
  facilities,
  selectedId,
  queryContext,
  onSelect,
  onOpen,
  onClearSelection,
}: FacilityMapProps) {
  const { t } = useI18n();
  const center = useMemo<[number, number]>(
    () =>
      queryContext
        ? [queryContext.location.latitude, queryContext.location.longitude]
        : [20.2961, 85.8245],
    [queryContext],
  );

  return (
    <section className="map-panel" aria-label="Facilities map">
      <div className="map-toolbar">
        <h2>
          {t.mapTitle} <span>· {queryContext?.location.resolvedName ?? "Bhubaneswar"}</span>
        </h2>
        <button
          className="icon-button"
          type="button"
          aria-label={t.mapCenter}
          title={t.mapCenter}
          onClick={onClearSelection}
        >
          <Crosshair size={18} />
        </button>
      </div>
      <div className="map-canvas">
        <MapContainer
          center={center}
          zoom={13}
          zoomControl={false}
          scrollWheelZoom
          className="leaflet-container"
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <MapViewport facilities={facilities} selectedId={selectedId} center={center} />
          <Marker position={center} icon={searchAreaIcon} title={t.searchArea} zIndexOffset={-100} />
          {facilities.map((facility) => (
            <Marker
              key={facility.id}
              position={[facility.latitude, facility.longitude]}
              icon={createMarkerIcon(facility, facility.id === selectedId)}
              eventHandlers={{
                click: () => onSelect(facility.id),
              }}
              zIndexOffset={facility.id === selectedId ? 1000 : 0}
            >
              <Popup className="facility-popup">
                <div className="map-popup-content">
                  <strong>{facility.name}</strong>
                  <span>
                    {t.kmAway(facility.distanceKm.toFixed(1))} · {facility.totalScore}/100 {t.matchScore}
                  </span>
                  <button type="button" onClick={() => onOpen(facility.id)}>
                    {t.seeProof} <ArrowRight size={14} />
                  </button>
                </div>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>
    </section>
  );
}
