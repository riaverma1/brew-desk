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
      "X-Goog-FieldMask": "places.id,places.displayName,places.location,places.formattedAddress,places.rating,places.userRatingCount,places.googleMapsUri",
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
  const places = (data.places ?? []).map((p: any) => ({
    id: p.id,
    name: p.displayName?.text ?? "Unknown",
    lat: p.location?.latitude,
    lng: p.location?.longitude,
    address: p.formattedAddress ?? null,
    rating: p.rating ?? null,
    userRatingCount: p.userRatingCount ?? null,
    mapsUrl: p.googleMapsUri ?? null,
  }));

  return NextResponse.json({ places });
}
