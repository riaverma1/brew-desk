import { NextResponse } from "next/server";

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || "http://localhost:8000";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const placeIds = searchParams.get("place_ids");

  if (!placeIds) {
    return NextResponse.json(
      { error: "Missing place_ids parameter" },
      { status: 400 }
    );
  }

  try {
    const response = await fetch(
      `${FASTAPI_BASE_URL}/api/places/data?place_ids=${placeIds}`,
      {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    if (!response.ok) {
      const errorText = await response.text();
      console.error("FastAPI data error:", errorText);
      return NextResponse.json(
        { error: "Backend API error", details: errorText },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error calling FastAPI data:", error);
    return NextResponse.json(
      {
        error: "Failed to fetch data",
        details: error instanceof Error ? error.message : String(error),
      },
      { status: 500 }
    );
  }
}
