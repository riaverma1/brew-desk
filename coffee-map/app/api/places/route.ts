import { NextResponse } from "next/server";

type Bounds = { north: number; south: number; east: number; west: number };

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || "http://localhost:8000";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);

  // Get bounds from query params
  const boundsParam = searchParams.get("bounds");
  if (!boundsParam) {
    return NextResponse.json(
      { error: "Missing bounds parameter" },
      { status: 400 }
    );
  }

  const bounds: Bounds = JSON.parse(boundsParam);

  // Calculate center and radius from bounds
  const lat = (bounds.north + bounds.south) / 2;
  const lng = (bounds.east + bounds.west) / 2;
  
  // Calculate approximate radius in meters
  // Using Haversine formula approximation for diagonal
  const R = 6371000; // Earth radius in meters
  const dLat = ((bounds.north - bounds.south) * Math.PI) / 180;
  const dLng = ((bounds.east - bounds.west) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((bounds.south * Math.PI) / 180) *
      Math.cos((bounds.north * Math.PI) / 180) *
      Math.sin(dLng / 2) *
      Math.sin(dLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  // Limit to small radius (500m) for initial zoomed-in view
  const radius = Math.min(Math.max(R * c, 300), 500); // Between 300m and 500m

  // Google Maps types filter
  const types = [
    "cafe",
    "coffee_shop",
    "bakery",
    "tea_house",
    // "sandwich_shop",
    // "breakfast_restaurant",
    // "brunch_restaurant",
    // "diner",
    // "restaurant",
    "library",
    "internet_cafe",
    "book_store",
    // "community_center",
    // "hotel",
    // "bed_and_breakfast",
    // "hostel",
    // "extended_stay_hotel",
    // "resort_hotel",
  ];

  try {
    // Call FastAPI backend
    const response = await fetch(`${FASTAPI_BASE_URL}/api/places/nearby-search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        lat,
        lng,
        radius: Math.round(radius),
        types,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("FastAPI error:", errorText);
      return NextResponse.json(
        { error: "Backend API error", details: errorText },
        { status: response.status }
      );
    }

    const data = await response.json();

    // Transform response to match frontend expectations
    // FastAPI already returns the correct format, so we can pass it through
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error calling FastAPI:", error);
    return NextResponse.json(
      { error: "Failed to fetch places", details: error instanceof Error ? error.message : String(error) },
      { status: 500 }
    );
  }
}
