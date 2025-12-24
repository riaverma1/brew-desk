"use client";

import { useEffect, useRef, useState } from "react";
import FilterSidebar, { WFHFilters } from "./components/FilterSidebar";
import EvidenceModal from "./components/EvidenceModal";

type Bounds = { north: number; south: number; east: number; west: number };

type DerivedAttribute = {
  value: string | string[];
  confidence: number;
  evidence: string[];
  sources: string[];
};

type EnrichedPlace = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  address?: string;
  rating?: number;
  userRatingCount?: number;
  types?: string[];
  website?: string;
  priceLevel?: string;
  businessStatus?: string;
  openingHours?: any;
  restroom?: boolean;
  servesCoffee?: boolean;
  outdoorSeating?: boolean;
  goodForGroups?: boolean;
  accessibilityOptions?: any;
  parkingOptions?: any;
  photos?: Array<{
    name: string;
    url: string;
    widthPx?: number;
    heightPx?: number;
    authorAttributions?: any[];
  }>;
  derived?: {
    has_wifi?: DerivedAttribute;
    has_outlets?: DerivedAttribute;
    is_laptop_friendly?: DerivedAttribute;
    noise_level?: DerivedAttribute;
    seating_availability?: DerivedAttribute;
    seating_comfort?: DerivedAttribute;
    open_after_7pm?: DerivedAttribute;
    notable_positives?: DerivedAttribute;
    common_complaints?: DerivedAttribute;
  };
  places_details_flag: boolean;
  enriched_flag: boolean;
  enriching?: boolean;
};

type EnrichmentStatus = {
  [place_id: string]: {
    places_details_flag: boolean;
    enriched_flag: boolean;
    enriching: boolean;
  };
};

export default function Home() {
  const mapRef = useRef<google.maps.Map | null>(null);
  const markersRef = useRef<google.maps.Marker[]>([]);
  const infoWindowRef = useRef<google.maps.InfoWindow | null>(null);
  const openInfoWindowPlaceIdRef = useRef<string | null>(null);
  const [places, setPlaces] = useState<EnrichedPlace[]>([]);
  const [filters, setFilters] = useState<WFHFilters>({});
  const [enrichingPlaces, setEnrichingPlaces] = useState<Set<string>>(new Set());
  const [evidenceModal, setEvidenceModal] = useState<{
    isOpen: boolean;
    attributeName: string;
    evidence: string[];
    sources: string[];
  }>({
    isOpen: false,
    attributeName: "",
    evidence: [],
    sources: [],
  });
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const fetchPlacesTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const evidenceDataRef = useRef<Map<string, { evidence: string[]; sources: string[] }>>(new Map());

  // Get user location and initialize map
  useEffect(() => {
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY}&libraries=places&v=weekly`;
    script.async = true;
    document.head.appendChild(script);

    script.onload = () => {
      // Get user location
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          (position) => {
            const userLat = position.coords.latitude;
            const userLng = position.coords.longitude;

            const map = new google.maps.Map(document.getElementById("map") as HTMLElement, {
              center: { lat: userLat, lng: userLng },
              zoom: 17,
            });

            mapRef.current = map;

            // Wait for map to be fully loaded before fetching places
            const idleListener = map.addListener("idle", () => {
              if (mapRef.current) {
                console.log("Map idle, fetching places...");
                fetchPlacesForBounds(mapRef.current);
                google.maps.event.removeListener(idleListener);
              }
            });

            // When the user stops moving the map, fetch new results
            map.addListener("idle", () => {
              if (mapRef.current) {
                fetchPlacesForBounds(mapRef.current);
              }
            });
          },
          () => {
            // Fallback to default location if geolocation fails
            const map = new google.maps.Map(document.getElementById("map") as HTMLElement, {
              center: { lat: 40.7831, lng: -73.9712 },
              zoom: 17,
            });
            mapRef.current = map;
            // Wait for map to be fully loaded
            const idleListener = map.addListener("idle", () => {
              if (mapRef.current) {
                console.log("Map idle (fallback), fetching places...");
                fetchPlacesForBounds(mapRef.current);
                google.maps.event.removeListener(idleListener);
              }
            });

            // When the user stops moving the map, fetch new results
            map.addListener("idle", () => {
              if (mapRef.current) {
                fetchPlacesForBounds(mapRef.current);
              }
            });
          }
        );
      } else {
        // Fallback if geolocation not available
        const map = new google.maps.Map(document.getElementById("map") as HTMLElement, {
          center: { lat: 40.7831, lng: -73.9712 },
          zoom: 17,
        });
        mapRef.current = map;
        
        // Wait for map to be fully loaded
        const idleListener = map.addListener("idle", () => {
          if (mapRef.current) {
            console.log("Map idle (no geolocation), fetching places...");
            fetchPlacesForBounds(mapRef.current);
            google.maps.event.removeListener(idleListener);
          }
        });

        // When the user stops moving the map, fetch new results
        map.addListener("idle", () => {
          if (mapRef.current) {
            fetchPlacesForBounds(mapRef.current);
          }
        });
      }
    };

    return () => {
      script.remove();
    };
  }, []);

  // Fetch places for current map bounds (with debouncing)
  const fetchPlacesForBounds = async (map: google.maps.Map) => {
    // Clear any pending fetch
    if (fetchPlacesTimeoutRef.current) {
      clearTimeout(fetchPlacesTimeoutRef.current);
    }

    // Debounce: wait 500ms after map stops moving before fetching
    fetchPlacesTimeoutRef.current = setTimeout(async () => {
      // Wait for map bounds to be ready
      const b = map.getBounds();
      if (!b) {
        console.log("Map bounds not ready yet, waiting...");
        // Wait a bit and try again
        setTimeout(() => {
          if (mapRef.current) {
            fetchPlacesForBounds(mapRef.current);
          }
        }, 500);
        return;
      }

      const ne = b.getNorthEast();
      const sw = b.getSouthWest();

      const bounds: Bounds = {
        north: ne.lat(),
        east: ne.lng(),
        south: sw.lat(),
        west: sw.lng(),
      };

      console.log("Fetching places for bounds:", bounds);

      try {
      const res = await fetch(`/api/places?bounds=${encodeURIComponent(JSON.stringify(bounds))}`);
      
      if (!res.ok) {
        const errorText = await res.text();
        console.error("API error:", res.status, errorText);
        return;
      }

      const data = await res.json();
      console.log("Received data:", data);

      if (data.error) {
        console.error("API returned error:", data.error);
        return;
      }

      if (data.places && Array.isArray(data.places)) {
        console.log(`Received ${data.places.length} places`);
        setPlaces(data.places);
        
        // Track enriching places
        if (data.enrichment_status) {
          const enriching = new Set<string>();
          Object.entries(data.enrichment_status).forEach(([placeId, status]: [string, any]) => {
            if (status.enriching || !status.enriched_flag) {
              enriching.add(placeId);
            }
          });
          setEnrichingPlaces(enriching);
          
          // Start polling if there are enriching places
          if (enriching.size > 0) {
            startPolling(Array.from(enriching));
          }
        }
      } else {
        console.warn("No places in response:", data);
      }
    } catch (error) {
      console.error("Error fetching places:", error);
    }
    }, 500); // 500ms debounce
  };

  // Poll for enrichment status
  const startPolling = (initialPlaceIds: string[]) => {
    // Clear existing polling
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }

    let placeIds = [...initialPlaceIds];

    pollingIntervalRef.current = setInterval(async () => {
      if (placeIds.length === 0) {
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
        return;
      }

      try {
        const FASTAPI_BASE_URL = process.env.NEXT_PUBLIC_FASTAPI_BASE_URL || "http://localhost:8000";
        const statusRes = await fetch(
          `${FASTAPI_BASE_URL}/api/places/status?place_ids=${placeIds.join(",")}`
        );
        const statusData = await statusRes.json();

        const stillEnriching = new Set<string>();
        const completed = new Set<string>();

        Object.entries(statusData).forEach(([placeId, status]: [string, any]) => {
          if (status.enriching || !status.enriched_flag) {
            stillEnriching.add(placeId);
          } else if (status.enriched_flag) {
            completed.add(placeId);
          }
        });

        setEnrichingPlaces(stillEnriching);

        // If any places completed enrichment, fetch updated data
        if (completed.size > 0) {
          const dataRes = await fetch(
            `${FASTAPI_BASE_URL}/api/places/data?place_ids=${Array.from(completed).join(",")}`
          );
          const data = await dataRes.json();

          if (data.places) {
            setPlaces((prevPlaces) => {
              const updated = [...prevPlaces];
              let hasChanges = false;
              data.places.forEach((newPlace: EnrichedPlace) => {
                const index = updated.findIndex((p) => p.id === newPlace.id);
                if (index >= 0) {
                  // Only update if data actually changed (avoid unnecessary re-renders)
                  const oldPlace = updated[index];
                  const placeChanged = JSON.stringify(oldPlace) !== JSON.stringify(newPlace);
                  if (placeChanged) {
                    updated[index] = newPlace;
                    hasChanges = true;
                  }
                }
              });
              // Only return new array if there were actual changes
              return hasChanges ? updated : prevPlaces;
            });
          }
        }

        // Update placeIds for next poll
        placeIds = Array.from(stillEnriching);
        if (placeIds.length === 0 && pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
      } catch (error) {
        console.error("Error polling enrichment status:", error);
      }
    }, 5000); // Poll every 5 seconds
  };

  // Cleanup polling and debounce timer on unmount
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
      if (fetchPlacesTimeoutRef.current) {
        clearTimeout(fetchPlacesTimeoutRef.current);
      }
    };
  }, []);

  // Filter places based on WFH filters
  const filteredPlaces = places.filter((place) => {
    // WiFi filter
    if (filters.has_wifi && filters.has_wifi.length > 0) {
      const wifiValue = place.derived?.has_wifi?.value;
      if (!wifiValue || !filters.has_wifi.includes(String(wifiValue))) {
        return false;
      }
    }

    // Outlets filter
    if (filters.has_outlets && filters.has_outlets.length > 0) {
      const outletsValue = place.derived?.has_outlets?.value;
      if (!outletsValue || !filters.has_outlets.includes(String(outletsValue))) {
        return false;
      }
    }

    // Laptop friendly filter
    if (filters.is_laptop_friendly && filters.is_laptop_friendly.length > 0) {
      const laptopValue = place.derived?.is_laptop_friendly?.value;
      if (!laptopValue || !filters.is_laptop_friendly.includes(String(laptopValue))) {
        return false;
      }
    }

    // Noise level filter
    if (filters.noise_level && filters.noise_level.length > 0) {
      const noiseValue = place.derived?.noise_level?.value;
      if (!noiseValue || !filters.noise_level.includes(String(noiseValue))) {
        return false;
      }
    }

    // Place detail attributes
    if (filters.restroom !== undefined && place.restroom !== filters.restroom) {
      return false;
    }
    if (filters.outdoorSeating !== undefined && place.outdoorSeating !== filters.outdoorSeating) {
      return false;
    }
    if (filters.servesCoffee !== undefined && place.servesCoffee !== filters.servesCoffee) {
      return false;
    }

    return true;
  });

  // Render markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      console.log("Map not ready for markers");
      return;
    }

    console.log(`Rendering ${filteredPlaces.length} filtered places`);

    // Check if InfoWindow is open for a place that still exists
    const openPlaceId = openInfoWindowPlaceIdRef.current;
    const openPlaceStillExists = openPlaceId && filteredPlaces.some(p => p.id === openPlaceId);
    
    // Clear old markers
    markersRef.current.forEach((m) => m.setMap(null));
    markersRef.current = [];
    
    // Only close InfoWindow if the place it's open for no longer exists
    if (infoWindowRef.current && !openPlaceStillExists) {
      infoWindowRef.current.close();
      openInfoWindowPlaceIdRef.current = null;
    }

    // Create or reuse info window
    if (!infoWindowRef.current) {
      infoWindowRef.current = new google.maps.InfoWindow();
    }
    const infoWindow = infoWindowRef.current;

    // Add markers for filtered places
    markersRef.current = filteredPlaces.map((place) => {
      if (!place.lat || !place.lng) {
        console.warn("Place missing coordinates:", place);
        return null;
      }
      // Create marker with default red Google Maps icon
      const marker = new google.maps.Marker({
        map,
        position: { lat: place.lat, lng: place.lng },
        title: place.name,
      });

      marker.addListener("click", () => {
        // Track which place the InfoWindow is open for
        openInfoWindowPlaceIdRef.current = place.id;
        
        // Build HTML content for InfoWindow
        const formatAttributeName = (name: string) => {
          return name.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
        };

        const formatAttributeValue = (attr: DerivedAttribute) => {
          if (Array.isArray(attr.value)) {
            return attr.value.join(", ");
          }
          return attr.value;
        };

        let attributesHtml = "";
        if (place.derived) {
          Object.entries(place.derived).forEach(([key, attr]) => {
            if (attr && attr.value !== "unknown" && !(Array.isArray(attr.value) && attr.value.length === 0)) {
              // Store evidence data in a ref with a unique key
              const evidenceKey = `${place.id}_${key}`;
              if (attr.evidence && attr.evidence.length > 0) {
                evidenceDataRef.current.set(evidenceKey, {
                  evidence: attr.evidence,
                  sources: attr.sources || []
                });
              }
              
              attributesHtml += `
                <div style="margin-bottom: 8px; font-size: 12px;">
                  <div style="font-weight: 600; margin-bottom: 4px;">
                    ${formatAttributeName(key)}: ${formatAttributeValue(attr)}
                    ${attr.confidence > 0 ? `<span style="color: #666; font-weight: 400; margin-left: 4px;">(${Math.round(attr.confidence * 100)}% confidence)</span>` : ""}
                  </div>
                  ${attr.evidence && attr.evidence.length > 0 ? `
                    <button 
                      onclick="window.showEvidence('${evidenceKey}', '${key}')"
                      style="background: #1976d2; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px;"
                    >
                      Show Evidence
                    </button>
                  ` : ""}
                </div>
              `;
            }
          });
        }

        let amenitiesHtml = "";
        if (place.restroom !== undefined || place.servesCoffee !== undefined || place.outdoorSeating !== undefined) {
          amenitiesHtml = `
            <div style="margin-top: 8px; margin-bottom: 8px; padding-top: 8px; border-top: 1px solid #eee;">
              <div style="font-size: 11px; font-weight: 600; margin-bottom: 4px; color: #666;">Amenities</div>
              ${place.restroom !== undefined ? `<div style="font-size: 12px; margin-bottom: 4px;"><strong>Restroom:</strong> ${place.restroom ? "Yes" : "No"}</div>` : ""}
              ${place.servesCoffee !== undefined ? `<div style="font-size: 12px; margin-bottom: 4px;"><strong>Serves Coffee:</strong> ${place.servesCoffee ? "Yes" : "No"}</div>` : ""}
              ${place.outdoorSeating !== undefined ? `<div style="font-size: 12px; margin-bottom: 4px;"><strong>Outdoor Seating:</strong> ${place.outdoorSeating ? "Yes" : "No"}</div>` : ""}
            </div>
          `;
        }

        const enrichmentStatusHtml = enrichingPlaces.has(place.id)
          ? `<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #eee; font-size: 11px; color: #666;">
               <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #ffa726; margin-right: 6px;"></span>
               Enrichment in progress...
             </div>`
          : "";

        // Build photos carousel HTML
        let photosHtml = "";
        if (place.photos && place.photos.length > 0) {
          const photosToShow = place.photos.slice(0, 5); // Show up to 5 photos
          photosHtml = `
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #eee;">
              <div style="font-size: 11px; font-weight: 600; margin-bottom: 6px; color: #666;">Photos</div>
              <div style="display: flex; gap: 6px; overflow-x: auto; padding-bottom: 4px;">
                ${photosToShow.map((photo: any) => `
                  <img 
                    src="${photo.url}" 
                    alt="${place.name}"
                    style="width: 80px; height: 80px; object-fit: cover; border-radius: 4px; flex-shrink: 0; cursor: pointer;"
                    onclick="window.open('${photo.url}', '_blank')"
                    onerror="this.style.display='none'"
                  />
                `).join("")}
              </div>
            </div>
          `;
        }

        // Build Google Maps link
        // Use place_id if available (new API format), otherwise use coordinates
        const googleMapsUrl = place.id 
          ? `https://www.google.com/maps/place/?q=place_id:${encodeURIComponent(place.id)}`
          : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place.lat)},${encodeURIComponent(place.lng)}`;
        const googleMapsButton = `
          <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #eee;">
            <a 
              href="${googleMapsUrl}" 
              target="_blank"
              rel="noopener noreferrer"
              style="display: inline-block; background: #4285f4; color: white; text-decoration: none; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 500;"
            >
              Open in Google Maps
            </a>
          </div>
        `;

        const html = `
          <div style="max-width: 300px; padding: 8px;">
            <div style="font-weight: 600; font-size: 14px; margin-bottom: 6px;">${place.name}</div>
            ${place.address ? `<div style="font-size: 12px; margin-bottom: 6px; color: #666;">${place.address}</div>` : ""}
            ${place.rating ? `<div style="font-size: 12px; margin-bottom: 6px;">⭐ ${place.rating} (${place.userRatingCount || 0} reviews)</div>` : ""}
            ${photosHtml}
            ${amenitiesHtml}
            ${attributesHtml ? `
              <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #eee;">
                <div style="font-size: 11px; font-weight: 600; margin-bottom: 4px; color: #666;">Work From Home Attributes</div>
                ${attributesHtml}
              </div>
            ` : ""}
            ${enrichmentStatusHtml}
            ${googleMapsButton}
          </div>
        `;

        // Store showEvidence function globally for InfoWindow buttons
        (window as any).showEvidence = (evidenceKey: string, attrName: string) => {
          const evidenceData = evidenceDataRef.current.get(evidenceKey);
          if (evidenceData) {
            setEvidenceModal({
              isOpen: true,
              attributeName: attrName,
              evidence: evidenceData.evidence,
              sources: evidenceData.sources,
            });
            infoWindow.close();
          }
        };

        infoWindow.setContent(html);
        infoWindow.open({ map, anchor: marker });
      });

      return marker;
    }).filter((m) => m !== null) as google.maps.Marker[];

    // If InfoWindow was open, re-open it on the new marker
    if (openPlaceStillExists && openPlaceId && infoWindowRef.current) {
      // Find the marker for the open place by matching place IDs
      const openPlaceIndex = filteredPlaces.findIndex(p => p.id === openPlaceId);
      if (openPlaceIndex >= 0 && openPlaceIndex < markersRef.current.length) {
        const markerForOpenPlace = markersRef.current[openPlaceIndex];
        if (markerForOpenPlace) {
          // Re-open the InfoWindow on the new marker
          // Trigger a click on the marker to rebuild and open the InfoWindow with latest data
          google.maps.event.trigger(markerForOpenPlace, 'click');
        }
      } else {
        // If we couldn't find the marker, just close the InfoWindow
        infoWindowRef.current.close();
        openInfoWindowPlaceIdRef.current = null;
      }
    }
  }, [filteredPlaces, enrichingPlaces]);

  return (
    <main style={{ height: "100vh", width: "100%", position: "relative" }}>
      <FilterSidebar filters={filters} onFiltersChange={setFilters} />

      <div id="map" style={{ height: "100%", width: "100%" }} />

      <EvidenceModal
        isOpen={evidenceModal.isOpen}
        onClose={() => setEvidenceModal({ ...evidenceModal, isOpen: false })}
        attributeName={evidenceModal.attributeName}
        evidence={evidenceModal.evidence}
        sources={evidenceModal.sources}
      />
    </main>
  );
}
