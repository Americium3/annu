import L from "leaflet";
import { useEffect, useMemo } from "react";
import {
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import { ArrowUpRight, Crosshair, MapPinned } from "lucide-react";
import type { FacilityRecommendation, QueryContext } from "../types";
import { MapLegend } from "./MapLegend";

interface FacilityMapProps {
  facilities: FacilityRecommendation[];
  selectedId?: string;
  queryContext?: QueryContext;
  onSelect: (id: string) => void;
  onOpen: (id: string) => void;
  onClearSelection: () => void;
}

function createMarkerIcon(facility: FacilityRecommendation, selected: boolean) {
  const scoreClass =
    facility.totalScore >= 85 ? "strong" : facility.totalScore >= 70 ? "mid" : "low";
  return L.divIcon({
    className: "custom-marker-wrapper",
    html: `<div class="custom-marker custom-marker-${scoreClass} ${selected ? "is-selected" : ""}"><span>${facility.rank}</span></div>`,
    iconSize: [38, 38],
    iconAnchor: [19, 19],
  });
}

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
        <div>
          <span className="map-eyebrow">
            <MapPinned size={15} />
            Explore nearby
          </span>
          <h2>{queryContext?.location.resolvedName ?? "Bhubaneswar"}</h2>
        </div>
        <button
          className="map-locate"
          type="button"
          aria-label="Center map on search area"
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
                  <span className="popup-rank">#{facility.rank} · Score {facility.totalScore}</span>
                  <strong>{facility.name}</strong>
                  <span>
                    {facility.distanceKm.toFixed(1)} km · {facility.type}
                  </span>
                  <button type="button" onClick={() => onOpen(facility.id)}>
                    See evidence <ArrowUpRight size={13} />
                  </button>
                </div>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
        <MapLegend />
        <div className="map-note">
          <span className="map-note-dot" />
          Facility pins are based on available coordinate data
        </div>
      </div>
    </section>
  );
}
