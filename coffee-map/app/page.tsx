"use client";

import { useEffect, useRef, useState } from "react";

type Bounds = { north: number; south: number; east: number; west: number };
type Place = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  address?: string | null;
  rating?: number | null;
  userRatingCount?: number | null;
  mapsUrl?: string | null;
};

export default function Home() {
  const mapRef = useRef<google.maps.Map | null>(null);
  const markersRef = useRef<google.maps.Marker[]>([]);
  const [places, setPlaces] = useState<Place[]>([]);
  const [onlyHighRated, setOnlyHighRated] = useState(false); // placeholder filter

  useEffect(() => {
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY}&libraries=places&v=weekly`;
    script.async = true;
    document.head.appendChild(script);

    script.onload = () => {
      const map = new google.maps.Map(document.getElementById("map") as HTMLElement, {
        center: { lat: 40.7831, lng: -73.9712 },
        zoom: 13,
      });

      mapRef.current = map;

      // When the user stops moving the map, fetch new results for this viewport
      map.addListener("idle", async () => {
        const b = map.getBounds();
        if (!b) return;

        const ne = b.getNorthEast();
        const sw = b.getSouthWest();

        const bounds: Bounds = {
          north: ne.lat(),
          east: ne.lng(),
          south: sw.lat(),
          west: sw.lng(),
        };

        const res = await fetch(`/api/places?bounds=${encodeURIComponent(JSON.stringify(bounds))}`);
        const data = await res.json();
        setPlaces(data.places ?? []);
      });
    };

    return () => {
      script.remove();
    };
  }, []);

  // Step 3 will render markers from `places`
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Clear old markers
    markersRef.current.forEach((m) => m.setMap(null));
    markersRef.current = [];

    const filtered = onlyHighRated
      ? places.filter((p) => (p.rating ?? 0) >= 4.3)
      : places;

    // Add new markers
    const info = new google.maps.InfoWindow();

    markersRef.current = filtered.map((p) => {
      const marker = new google.maps.Marker({
        map,
        position: { lat: p.lat, lng: p.lng },
        title: p.name,
      });

      marker.addListener("click", () => {
        const html = `
          <div style="max-width:240px">
            <div style="font-weight:600">${p.name}</div>
            <div style="font-size:12px; margin:6px 0">${p.address ?? ""}</div>
            <div style="font-size:12px">⭐ ${p.rating ?? "—"} (${p.userRatingCount ?? 0})</div>
            ${p.mapsUrl ? `<div style="margin-top:8px"><a href="${p.mapsUrl}" target="_blank" rel="noreferrer">Open in Google Maps</a></div>` : ""}
          </div>
        `;
        info.setContent(html);
        info.open({ map, anchor: marker });
      });

      return marker;
    });
  }, [places, onlyHighRated]);

  return (
    <main style={{ height: "100vh", width: "100%", position: "relative" }}>
      {/* Step 4: simple filter checkbox */}
      <div style={{ position: "absolute", top: 12, left: 12, zIndex: 10, background: "white", padding: 10, borderRadius: 8 }}>
        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={onlyHighRated}
            onChange={(e) => setOnlyHighRated(e.target.checked)}
          />
          Placeholder filter: only show rating ≥ 4.3
        </label>
        <div style={{ fontSize: 12, marginTop: 6, color: "#555" }}>
          (Later this becomes wifi/outlets)
        </div>
      </div>

      <div id="map" style={{ height: "100%", width: "100%" }} />
    </main>
  );
}
