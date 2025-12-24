import { NextResponse } from "next/server";

type Bounds = { north: number; south: number; east: number; west: number };

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);

  // We’ll pass bounds from the frontend soon. For now, default to a Manhattan-ish box.
  const boundsParam = searchParams.get("bounds");
  const bounds: Bounds = boundsParam
    ? JSON.parse(boundsParam)
    : { north: 40.8008, south: 40.7306, east: -73.9533, west: -74.0104 };

  const apiKey = process.env.GOOGLE_PLACES_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "Missing GOOGLE_PLACES_API_KEY in .env.local" },
      { status: 500 }
    );
  }

  // Center of the viewport bounding box
  const lat = (bounds.north + bounds.south) / 2;
  const lng = (bounds.east + bounds.west) / 2;

  const body = {
    includedTypes: ["cafe"],
    maxResultCount: 20,
    locationRestriction: {
      circle: {
        center: { latitude: lat, longitude: lng },
        radius: 1200.0, // meters (tune later)
      },
    },
  };

  const resp = await fetch("https://places.googleapis.com/v1/places:searchNearby", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Goog-Api-Key": apiKey,
      // Field mask controls response size + cost
      "X-Goog-FieldMask": "places.id,places.displayName,places.location,places.formattedAddress,places.rating,places.userRatingCount,places.googleMapsUri,places.photos",
    },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    return NextResponse.json(
      { error: "Places API error", status: resp.status, details: errText },
      { status: 500 }
    );
  }

  const data = await resp.json();
  
  // Helper function to process photos (prefer interior, limit to 2-5)
  const processPhotos = (photos: any[] | undefined, apiKey: string): any[] => {
    if (!photos || photos.length === 0) return [];
    
    // Separate interior and other photos
    const interiorPhotos: any[] = [];
    const otherPhotos: any[] = [];
    
    for (const photo of photos) {
      const photoTypes = photo.photoTypes || [];
      const isInterior = photoTypes.some((pt: string) => 
        pt.toUpperCase().includes("INTERIOR")
      );
      
      if (isInterior) {
        interiorPhotos.push(photo);
      } else {
        otherPhotos.push(photo);
      }
    }
    
    // Prefer interior photos, but include others if needed
    let selectedPhotos: any[] = [];
    selectedPhotos.push(...interiorPhotos.slice(0, 5));
    
    if (selectedPhotos.length < 5) {
      const remaining = 5 - selectedPhotos.length;
      selectedPhotos.push(...otherPhotos.slice(0, remaining));
    }
    
    // Ensure at least 2 photos if available, but limit to 5
    if (selectedPhotos.length < 2 && photos.length >= 2) {
      selectedPhotos = photos.slice(0, Math.min(5, photos.length));
    }
    
    selectedPhotos = selectedPhotos.slice(0, 5);
    
    // Generate photo URLs
    return selectedPhotos
      .filter((photo) => photo.name)
      .map((photo) => ({
        name: photo.name,
        url: `https://places.googleapis.com/v1/${photo.name}/media?maxHeightPx=400&maxWidthPx=400&key=${apiKey}`,
        widthPx: photo.widthPx,
        heightPx: photo.heightPx,
        authorAttributions: photo.authorAttributions || [],
      }));
  };
  
  const places = (data.places ?? []).map((p: any) => ({
    id: p.id,
    name: p.displayName?.text ?? "Unknown",
    lat: p.location?.latitude,
    lng: p.location?.longitude,
    address: p.formattedAddress ?? null,
    rating: p.rating ?? null,
    userRatingCount: p.userRatingCount ?? null,
    mapsUrl: p.googleMapsUri ?? null,
    photos: processPhotos(p.photos, apiKey),
  }));

  return NextResponse.json({ places });
}
