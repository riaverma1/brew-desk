"use client";

import { useEffect, useRef, useState } from "react";

type Bounds = { north: number; south: number; east: number; west: number };
type Photo = {
  name: string;
  url: string;
  widthPx?: number;
  heightPx?: number;
  authorAttributions?: Array<{ displayName?: string; uri?: string }>;
};

type Place = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  address?: string | null;
  rating?: number | null;
  userRatingCount?: number | null;
  mapsUrl?: string | null;
  photos?: Photo[];
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
        // Build photo carousel HTML if photos are available
        let photosHtml = "";
        if (p.photos && p.photos.length > 0) {
          const photoItems = p.photos
            .slice(0, 5) // Limit to 5 photos
            .map(
              (photo) => `
            <div style="flex: 0 0 auto; width: 120px; margin-right: 8px;">
              <img 
                src="${photo.url}" 
                alt="${p.name}"
                style="width: 120px; height: 90px; object-fit: cover; border-radius: 4px; cursor: pointer;"
                onclick="window.open('${photo.url}', '_blank')"
                onerror="this.style.display='none'"
              />
            </div>
          `
            )
            .join("");
          
          photosHtml = `
            <div style="margin: 12px 0; padding: 8px 0; border-top: 1px solid #eee; border-bottom: 1px solid #eee;">
              <div style="font-size: 11px; color: #666; margin-bottom: 6px;">Photos</div>
              <div style="display: flex; overflow-x: auto; gap: 0; scrollbar-width: thin; -webkit-overflow-scrolling: touch;">
                ${photoItems}
              </div>
            </div>
          `;
        }
        
        const html = `
          <div style="max-width:280px">
            <div style="font-weight:600; font-size:14px; margin-bottom:6px">${p.name}</div>
            <div style="font-size:12px; margin:6px 0; color:#666">${p.address ?? ""}</div>
            <div style="font-size:12px; margin:6px 0">⭐ ${p.rating ?? "—"} (${p.userRatingCount ?? 0} reviews)</div>
            ${photosHtml}
            ${p.mapsUrl ? `<div style="margin-top:8px"><a href="${p.mapsUrl}" target="_blank" rel="noreferrer" style="font-size:12px; color:#1976d2; text-decoration:none">Open in Google Maps →</a></div>` : ""}
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
