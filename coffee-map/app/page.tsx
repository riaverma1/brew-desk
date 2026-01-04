"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import FilterSidebar, { WFHFilters } from "./components/FilterSidebar";
import EvidenceModal from "./components/EvidenceModal";

// TypeScript declaration for Google Maps
declare global {
  interface Window {
    google: typeof google;
    showEvidence: (evidenceKey: string, attrName: string) => void;
    enrichPlace: (placeId: string) => Promise<void>;
  }
}

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
  nearby_search_flag?: boolean;
  places_details_flag: boolean;
  tavily_flag?: boolean;
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
  const [isLoadingPlaces, setIsLoadingPlaces] = useState(false);
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
  const fetchPlacesAbortControllerRef = useRef<AbortController | null>(null);
  const infoWindowOpenTimeRef = useRef<number | null>(null);
  const evidenceDataRef = useRef<Map<string, { evidence: string[]; sources: string[] }>>(new Map());

  // Get user location and initialize map
  useEffect(() => {
    // Check if Google Maps is already loaded
    if (window.google && window.google.maps) {
      console.log("Google Maps already loaded");
      initializeMap();
      return;
    }

    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY}&libraries=places&v=weekly`;
    script.async = true;
    
    script.onerror = () => {
      console.error("Failed to load Google Maps script");
    };

    script.onload = () => {
      console.log("Google Maps script loaded");
      initializeMap();
    };

    document.head.appendChild(script);

    function initializeMap() {
      const mapElement = document.getElementById("map");
      if (!mapElement) {
        console.error("Map element not found - retrying in 100ms");
        setTimeout(initializeMap, 100);
        return;
      }

      console.log("Map element found, initializing map...");

      // Get user location
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          (position) => {
            const userLat = position.coords.latitude;
            const userLng = position.coords.longitude;

            try {
              if (!window.google || !window.google.maps) {
                console.error("Google Maps API not available");
                return;
              }

              const map = new google.maps.Map(mapElement, {
                center: { lat: userLat, lng: userLng },
                zoom: 17,
              });

              mapRef.current = map;
              console.log("Map initialized successfully at", userLat, userLng);

              // Wait for map to be fully loaded before fetching places
              const idleListener = map.addListener("idle", () => {
                if (mapRef.current) {
                  console.log("Map idle, fetching places...");
                  fetchPlacesForBounds(mapRef.current);
                  google.maps.event.removeListener(idleListener);
                }
              });

              // When the user stops moving the map, fetch new results
              // But ignore idle events that occur shortly after InfoWindow opens (to prevent auto-pan from triggering searches)
              map.addListener("idle", () => {
                if (mapRef.current) {
                  // Ignore idle events within 500ms of opening an InfoWindow (prevents auto-pan from triggering searches)
                  const now = Date.now();
                  if (infoWindowOpenTimeRef.current && (now - infoWindowOpenTimeRef.current) < 500) {
                    console.log("Ignoring idle event (InfoWindow was just opened)");
                    return;
                  }
                  fetchPlacesForBounds(mapRef.current);
                }
              });
            } catch (error) {
              console.error("Error initializing map:", error);
              // Try to show a helpful error message
              if (mapElement) {
                mapElement.innerHTML = `<div style="padding: 20px; text-align: center; color: red;">
                  <p>Failed to initialize map</p>
                  <p style="font-size: 12px;">${error instanceof Error ? error.message : String(error)}</p>
                </div>`;
              }
            }
          },
          (error: GeolocationPositionError) => {
            console.warn("Geolocation failed:", error);
            // Fallback to default location if geolocation fails
            try {
              if (!window.google || !window.google.maps) {
                console.error("Google Maps API not available (fallback)");
                return;
              }

              const map = new google.maps.Map(mapElement, {
                center: { lat: 40.7831, lng: -73.9712 },
                zoom: 17,
              });
              mapRef.current = map;
              console.log("Map initialized successfully (fallback) at 40.7831, -73.9712");
            // Wait for map to be fully loaded
            const idleListener = map.addListener("idle", () => {
              if (mapRef.current) {
                console.log("Map idle (fallback), fetching places...");
                fetchPlacesForBounds(mapRef.current);
                google.maps.event.removeListener(idleListener);
              }
            });

            // When the user stops moving the map, fetch new results
            // But ignore idle events that occur shortly after InfoWindow opens (to prevent auto-pan from triggering searches)
            map.addListener("idle", () => {
              if (mapRef.current) {
                // Ignore idle events within 500ms of opening an InfoWindow (prevents auto-pan from triggering searches)
                const now = Date.now();
                if (infoWindowOpenTimeRef.current && (now - infoWindowOpenTimeRef.current) < 500) {
                  console.log("Ignoring idle event (InfoWindow was just opened)");
                  return;
                }
                fetchPlacesForBounds(mapRef.current);
              }
            });
            } catch (error) {
              console.error("Error initializing map (fallback):", error);
              if (mapElement) {
                mapElement.innerHTML = `<div style="padding: 20px; text-align: center; color: red;">
                  <p>Failed to initialize map (fallback)</p>
                  <p style="font-size: 12px;">${error instanceof Error ? error.message : String(error)}</p>
                </div>`;
              }
            }
          }
        );
              } else {
                console.log("Geolocation not available, using default location");
                // Fallback if geolocation not available
                try {
                  if (!window.google || !window.google.maps) {
                    console.error("Google Maps API not available (no geolocation)");
                    return;
                  }

                  const map = new google.maps.Map(mapElement, {
                    center: { lat: 40.7831, lng: -73.9712 },
                    zoom: 17,
                  });
                  mapRef.current = map;
                  console.log("Map initialized successfully (no geolocation) at 40.7831, -73.9712");
                
                // Wait for map to be fully loaded
                const idleListener = map.addListener("idle", () => {
                  if (mapRef.current) {
                    console.log("Map idle (no geolocation), fetching places...");
                    fetchPlacesForBounds(mapRef.current);
                    google.maps.event.removeListener(idleListener);
                  }
                });

                // When the user stops moving the map, fetch new results
                // But ignore idle events that occur shortly after InfoWindow opens (to prevent auto-pan from triggering searches)
                map.addListener("idle", () => {
                  if (mapRef.current) {
                    // Ignore idle events within 500ms of opening an InfoWindow (prevents auto-pan from triggering searches)
                    const now = Date.now();
                    if (infoWindowOpenTimeRef.current && (now - infoWindowOpenTimeRef.current) < 500) {
                      console.log("Ignoring idle event (InfoWindow was just opened)");
                      return;
                    }
                    fetchPlacesForBounds(mapRef.current);
                  }
                });
              } catch (error) {
                console.error("Error initializing map (no geolocation):", error);
                if (mapElement) {
                  mapElement.innerHTML = `<div style="padding: 20px; text-align: center; color: red;">
                    <p>Failed to initialize map (no geolocation)</p>
                    <p style="font-size: 12px;">${error instanceof Error ? error.message : String(error)}</p>
                  </div>`;
                }
              }
            }
    }

    return () => {
      // Cleanup handled by React
    };
  }, []);

  // Fetch places for current map bounds (with debouncing and request cancellation)
  const fetchPlacesForBounds = async (map: google.maps.Map) => {
    // Cancel any pending fetch request
    if (fetchPlacesAbortControllerRef.current) {
      fetchPlacesAbortControllerRef.current.abort();
    }
    
    // Clear any pending timeout
    if (fetchPlacesTimeoutRef.current) {
      clearTimeout(fetchPlacesTimeoutRef.current);
    }

    // Debounce: wait 800ms after map stops moving before fetching
    // This gives users time to pause before triggering a new search
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

      // Set loading state
      setIsLoadingPlaces(true);

      // Create a new AbortController for this request
      const abortController = new AbortController();
      fetchPlacesAbortControllerRef.current = abortController;

      try {
        const res = await fetch(`/api/places?bounds=${encodeURIComponent(JSON.stringify(bounds))}`, {
          signal: abortController.signal,
        });
        
        // Check if the request was aborted
        if (abortController.signal.aborted) {
          console.log("Request was aborted, ignoring response");
          // Don't clear loading state here - let finally block handle it
          return;
        }
        
        if (!res.ok) {
          const errorText = await res.text();
          console.error("API error:", res.status, errorText);
          // Set empty places array on error
          setPlaces([]);
          // Don't clear loading state here - let finally block handle it
          return;
        }

        const data = await res.json();
        
        // Check again if aborted after JSON parsing (may have taken time)
        if (abortController.signal.aborted) {
          console.log("Request was aborted after parsing, ignoring response");
          // Don't clear loading state here - let finally block handle it
          return;
        }
        
        console.log("Received data:", data);

        if (data.error) {
          console.error("API returned error:", data.error);
          setPlaces([]);  // Set empty array on error
          // Don't clear loading state here - let finally block handle it
          return;
        }

        if (data.places && Array.isArray(data.places)) {
          console.log(`Received ${data.places.length} places`);
          setPlaces(data.places);
          
          // Track enriching places (only places that are actively being enriched, not just unenriched)
          if (data.enrichment_status) {
            const enriching = new Set<string>();
            Object.entries(data.enrichment_status).forEach(([placeId, status]: [string, any]) => {
              // Only mark as enriching if status.enriching is true (actively being enriched)
              // Don't mark unenriched places as "enriching" - they should show the Enrich button
              if (status.enriching === true) {
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
          // Set empty array to prevent undefined errors
          setPlaces([]);
        }
      } catch (error) {
        // Ignore abort errors (expected when cancelling requests)
        if (error instanceof Error && error.name === 'AbortError') {
          console.log("Request was aborted");
          // Don't clear loading state here - let finally block handle it
          return;
        }
        console.error("Error fetching places:", error);
        // Only set empty array if not aborted
        if (!abortController.signal.aborted) {
          setPlaces([]);
        }
        // Don't clear loading state here - let finally block handle it
      } finally {
        // Clear the abort controller ref if this was the current request
        // Only clear loading state if this is still the active request (wasn't replaced by a newer one)
        if (fetchPlacesAbortControllerRef.current === abortController) {
          fetchPlacesAbortControllerRef.current = null;
          setIsLoadingPlaces(false);
        }
      }
    }, 800); // 800ms debounce - increased from 500ms to give more pause time
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
        const statusRes = await fetch(
          `/api/places/status?place_ids=${placeIds.join(",")}`
        );
        const statusData = await statusRes.json();

        const stillEnriching = new Set<string>();
        const completed = new Set<string>();

        Object.entries(statusData).forEach(([placeId, status]: [string, any]) => {
          // Only track places that are actively being enriched (status.enriching === true)
          // Don't track unenriched places - they should show the Enrich button
          if (status.enriching === true) {
            stillEnriching.add(placeId);
          } else if (status.enriched_flag) {
            completed.add(placeId);
          }
        });

        setEnrichingPlaces(stillEnriching);

        // If any places completed enrichment, fetch updated data
        if (completed.size > 0) {
          const dataRes = await fetch(
            `/api/places/data?place_ids=${Array.from(completed).join(",")}`
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
                  // Fast comparison: check key fields instead of full JSON.stringify
                  const oldPlace = updated[index];
                  const placeChanged = 
                    oldPlace.enriched_flag !== newPlace.enriched_flag ||
                    oldPlace.places_details_flag !== newPlace.places_details_flag ||
                    (oldPlace as any).tavily_flag !== (newPlace as any).tavily_flag ||
                    (oldPlace.derived && newPlace.derived && 
                     JSON.stringify(oldPlace.derived) !== JSON.stringify(newPlace.derived));
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

  // Cleanup polling, debounce timer, and abort in-flight requests on unmount
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
      if (fetchPlacesTimeoutRef.current) {
        clearTimeout(fetchPlacesTimeoutRef.current);
      }
      if (fetchPlacesAbortControllerRef.current) {
        fetchPlacesAbortControllerRef.current.abort();
      }
    };
  }, []);

  // Filter places based on WFH filters (memoized for performance)
  const filteredPlaces = useMemo(() => {
    const startTime = performance.now();
    const filtered = places.filter((place) => {
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
    const endTime = performance.now();
    console.log(`Filtering took ${(endTime - startTime).toFixed(2)}ms for ${places.length} places, result: ${filtered.length}`);
    return filtered;
  }, [places, filters]);

  // Helper function to build InfoWindow HTML content
  const buildInfoWindowContent = (place: EnrichedPlace): string => {
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

    // Build Enrich button (only show if not enriched)
    const enrichButtonHtml = !place.enriched_flag && !enrichingPlaces.has(place.id)
      ? `
        <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #eee;">
          <button 
            id="enrich-btn-${place.id}"
            onclick="window.enrichPlace('${place.id}')"
            style="background: #4caf50; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 500; width: 100%;"
          >
            Enrich
          </button>
        </div>
      `
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

    // Build enriching icon (shows when place is being enriched)
    let enrichingIcon = "";
    const isEnriching = enrichingPlaces.has(place.id) || place.enriching === true;
    if (isEnriching) {
      enrichingIcon = `
        <span 
          style="
            display: inline-block;
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background: #ffa726;
            color: white;
            font-size: 10px;
            line-height: 16px;
            text-align: center;
            margin-left: 6px;
            cursor: help;
            vertical-align: middle;
            position: relative;
            animation: pulse 2s infinite;
          "
          title="Enrichment in progress..."
        >
          ⟳
        </span>
        <style>
          @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
          }
        </style>
      `;
    }

    // Build Tavily status icon with tooltip (only show if enriched)
    let tavilyStatusIcon = "";
    if (place.enriched_flag) {
      const hasTavily = place.tavily_flag === true;
      const tooltipText = hasTavily 
        ? "Enriched with Tavily web search" 
        : "Enriched without Tavily (Google Places only)";
      const iconColor = hasTavily ? "#4CAF50" : "#FF9800";
      const iconSymbol = hasTavily ? "✓" : "ℹ";
      
      tavilyStatusIcon = `
        <span 
          style="
            display: inline-block;
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background: ${iconColor};
            color: white;
            font-size: 10px;
            line-height: 16px;
            text-align: center;
            margin-left: 6px;
            cursor: help;
            vertical-align: middle;
            position: relative;
          "
          title="${tooltipText}"
        >
          ${iconSymbol}
        </span>
      `;
    }

    return `
      <div style="max-width: 300px; padding: 8px;">
        <div style="font-weight: 600; font-size: 14px; margin-bottom: 6px; display: flex; align-items: center;">
          ${place.name}${enrichingIcon}${tavilyStatusIcon}
        </div>
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
        ${enrichButtonHtml}
        ${googleMapsButton}
      </div>
    `;
  };

  // Render markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      console.log("Map not ready for markers");
      return;
    }

    const renderStartTime = performance.now();
    console.log(`Rendering ${filteredPlaces.length} filtered places`);

    // Check if InfoWindow is open for a place that still exists
    const openPlaceId = openInfoWindowPlaceIdRef.current;
    const openPlaceStillExists = openPlaceId && filteredPlaces.some(p => p.id === openPlaceId);
    
    // Track if InfoWindow was visible before clearing markers
    // We'll use a ref to track this since we can't query InfoWindow visibility directly
    const wasInfoWindowVisible = openPlaceId !== null;
    
    // Clear old markers
    markersRef.current.forEach((m) => m.setMap(null));
    markersRef.current = [];
    
    // Close InfoWindow only if the place it's open for no longer exists
    // Don't close if it was manually closed (openInfoWindowPlaceIdRef is null) - that's already handled
    if (infoWindowRef.current && !openPlaceStillExists && openPlaceId) {
      infoWindowRef.current.close();
      openInfoWindowPlaceIdRef.current = null;
    }

    // Create or reuse info window
    if (!infoWindowRef.current) {
      infoWindowRef.current = new google.maps.InfoWindow();
      // Listen for when user closes the InfoWindow (clicks X)
      infoWindowRef.current.addListener("closeclick", () => {
        openInfoWindowPlaceIdRef.current = null;
      });
    }
    const infoWindow = infoWindowRef.current;

    // Add markers for filtered places
    markersRef.current = filteredPlaces.map((place) => {
      if (!place.lat || !place.lng) {
        console.warn("Place missing coordinates:", place);
        return null;
      }
      // Check if place is being enriched
      const isEnriching = enrichingPlaces.has(place.id) || place.enriching === true;
      
      // Create marker with icon based on enrichment status
      const marker = new google.maps.Marker({
        map,
        position: { lat: place.lat, lng: place.lng },
        title: isEnriching ? `${place.name} (Enriching...)` : place.name,
        // Use a different icon color if enriching
        icon: isEnriching ? {
          path: google.maps.SymbolPath.CIRCLE,
          scale: 8,
          fillColor: "#ffa726",
          fillOpacity: 1,
          strokeColor: "#ffffff",
          strokeWeight: 2,
        } : undefined, // Default red marker if not enriching
      });

      marker.addListener("click", () => {
        // Track which place the InfoWindow is open for
        openInfoWindowPlaceIdRef.current = place.id;
        
        // Build HTML content using helper function
        const html = buildInfoWindowContent(place);

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

        // Store enrichPlace function globally for InfoWindow buttons
        (window as any).enrichPlace = async (placeId: string) => {
          const button = document.getElementById(`enrich-btn-${placeId}`);
          
          if (button) {
            button.textContent = "Enriching...";
            (button as HTMLButtonElement).disabled = true;
            (button as HTMLButtonElement).style.background = "#ccc";
          }
          
          // Add to enriching places set
          setEnrichingPlaces((prev) => new Set(prev).add(placeId));
          
          try {
            const response = await fetch(`/api/places/enrich/${placeId}`, {
              method: "POST",
            });
            
            if (!response.ok) {
              throw new Error(`Enrichment failed: ${response.statusText}`);
            }
            
            const enrichedPlace = await response.json();
            
            // Update the place in the places array and refresh InfoWindow
            setPlaces((prevPlaces) => {
              const updated = prevPlaces.map((p) => 
                p.id === placeId ? { ...p, ...enrichedPlace } : p
              );
              const updatedPlace = updated.find((p) => p.id === placeId);
              if (updatedPlace && infoWindowRef.current && openInfoWindowPlaceIdRef.current === placeId) {
                const updatedHtml = buildInfoWindowContent(updatedPlace);
                infoWindowRef.current.setContent(updatedHtml);
              }
              return updated;
            });
            
            // Remove from enriching places
            setEnrichingPlaces((prev) => {
              const next = new Set(prev);
              next.delete(placeId);
              return next;
            });
          } catch (error) {
            console.error("Error enriching place:", error);
            if (button) {
              button.textContent = "Enrich (Failed - Click to Retry)";
              (button as HTMLButtonElement).disabled = false;
              (button as HTMLButtonElement).style.background = "#4caf50";
            }
            setEnrichingPlaces((prev) => {
              const next = new Set(prev);
              next.delete(placeId);
              return next;
            });
          }
        };

        infoWindow.setContent(html);
        // Track when InfoWindow opens to prevent auto-pan from triggering new searches
        infoWindowOpenTimeRef.current = Date.now();
        infoWindow.open({ map, anchor: marker });
      });

      return marker;
    }).filter((m) => m !== null) as google.maps.Marker[];

    // If InfoWindow was open before re-rendering, re-attach it to the new marker
    // This keeps it open when the user scrolls (markers are re-rendered)
    // Note: If user manually closed it, openInfoWindowPlaceIdRef.current will be null
    // (set by the closeclick listener), so we won't re-open it
    if (wasInfoWindowVisible && openPlaceStillExists && openPlaceId && infoWindowRef.current) {
      const openPlace = filteredPlaces.find(p => p.id === openPlaceId);
      const openPlaceIndex = filteredPlaces.findIndex(p => p.id === openPlaceId);
      if (openPlace && openPlaceIndex >= 0 && openPlaceIndex < markersRef.current.length) {
        const markerForOpenPlace = markersRef.current[openPlaceIndex];
        if (markerForOpenPlace) {
          // Re-open the InfoWindow on the new marker without triggering click (no panning)
          // Rebuild content with latest place data
          const html = buildInfoWindowContent(openPlace);
          infoWindowRef.current.setContent(html);
          // Track when InfoWindow re-opens to prevent auto-pan from triggering new searches
          infoWindowOpenTimeRef.current = Date.now();
          infoWindowRef.current.open({ map, anchor: markerForOpenPlace });
        }
      }
    } else if (openPlaceId && !openPlaceStillExists) {
      // Place no longer exists in filtered results, clear the ref
      openInfoWindowPlaceIdRef.current = null;
    }
    const renderEndTime = performance.now();
    console.log(`Marker rendering took ${(renderEndTime - renderStartTime).toFixed(2)}ms`);
  }, [filteredPlaces, enrichingPlaces]);

  return (
    <main style={{ height: "100vh", width: "100%", position: "relative", overflow: "hidden" }}>
      <FilterSidebar filters={filters} onFiltersChange={setFilters} />

      {/* Loading Indicator */}
      {isLoadingPlaces && (
        <div
          style={{
            position: "absolute",
            top: "12px",
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 10,
            background: "white",
            padding: "8px 16px",
            borderRadius: "8px",
            boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
            fontSize: "12px",
            fontWeight: 500,
            color: "#1976d2",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <div
            style={{
              width: "16px",
              height: "16px",
              border: "2px solid #1976d2",
              borderTopColor: "transparent",
              borderRadius: "50%",
              animation: "spin 0.8s linear infinite",
            }}
          />
          Loading places...
          <style>{`
            @keyframes spin {
              to { transform: rotate(360deg); }
            }
          `}</style>
        </div>
      )}

      {/* Enrichment Status Legend */}
      <div
        style={{
          position: "absolute",
          top: "12px",
          right: "12px",
          zIndex: 10,
          background: "white",
          padding: "12px 16px",
          borderRadius: "8px",
          boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
          fontSize: "11px",
          maxWidth: "200px",
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: "8px", fontSize: "12px", color: "#333" }}>
          Enrichment Status
        </div>
        <div style={{ display: "flex", alignItems: "center", marginBottom: "6px" }}>
          <span
            style={{
              display: "inline-block",
              width: "16px",
              height: "16px",
              borderRadius: "50%",
              background: "#4CAF50",
              color: "white",
              fontSize: "10px",
              lineHeight: "16px",
              textAlign: "center",
              marginRight: "8px",
              flexShrink: 0,
            }}
            title="Enriched with Tavily web search"
          >
            ✓
          </span>
          <span style={{ color: "#666" }}>With Tavily</span>
        </div>
        <div style={{ display: "flex", alignItems: "center" }}>
          <span
            style={{
              display: "inline-block",
              width: "16px",
              height: "16px",
              borderRadius: "50%",
              background: "#FF9800",
              color: "white",
              fontSize: "10px",
              lineHeight: "16px",
              textAlign: "center",
              marginRight: "8px",
              flexShrink: 0,
            }}
            title="Enriched without Tavily (Google Places only)"
          >
            ℹ
          </span>
          <span style={{ color: "#666" }}>Google Only</span>
        </div>
      </div>

      <div 
        id="map" 
        style={{ 
          height: "100%", 
          width: "100%", 
          position: "absolute",
          top: 0,
          left: 0,
          zIndex: 0
        }} 
      />

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
