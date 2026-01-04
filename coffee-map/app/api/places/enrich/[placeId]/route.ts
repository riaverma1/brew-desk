import { NextResponse } from "next/server";

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || "http://localhost:8000";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ placeId: string }> }
) {
  const { placeId } = await params;

  if (!placeId) {
    return NextResponse.json(
      { error: "Missing placeId parameter" },
      { status: 400 }
    );
  }

  try {
    const response = await fetch(
      `${FASTAPI_BASE_URL}/api/places/enrich/${placeId}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    if (!response.ok) {
      const errorText = await response.text();
      console.error("FastAPI enrich error:", errorText);
      return NextResponse.json(
        { error: "Backend API error", details: errorText },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error calling FastAPI enrich:", error);
    return NextResponse.json(
      {
        error: "Failed to trigger enrichment",
        details: error instanceof Error ? error.message : String(error),
      },
      { status: 500 }
    );
  }
}
