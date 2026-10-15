"use client";

import "leaflet/dist/leaflet.css";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import type { GeoMappingResult } from "@/lib/api/types";

const GERMANY_CENTER: [number, number] = [51.1657, 10.4515];

function colorFor(item: GeoMappingResult): string {
  if (item.status === "blocked") return "#EF4444";
  if (item.status === "active") return "#22C55E";
  return "#94A3B8";
}

export function GeoMap({ results }: { results: GeoMappingResult[] }) {
  const points = results.filter((item) => item.latitude != null && item.longitude != null);

  return (
    <MapContainer
      center={GERMANY_CENTER}
      zoom={6}
      scrollWheelZoom={false}
      className="h-[360px] w-full rounded-xl"
      style={{ background: "#0D1B2E" }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {points.map((item) => (
        <CircleMarker
          key={item.id}
          center={[item.latitude as number, item.longitude as number]}
          radius={7}
          pathOptions={{ color: colorFor(item), fillColor: colorFor(item), fillOpacity: 0.85, weight: 1 }}
        >
          <Popup>
            <strong>{item.name}</strong>
            <br />
            Kunde · {item.location}
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
