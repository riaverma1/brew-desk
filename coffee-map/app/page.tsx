"use client";

import { useEffect } from "react";

export default function Home() {
  useEffect(() => {
    fetch("/api/places")
      .then((res) => res.json())
      .then((data) => console.log("API response:", data));

    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY}&libraries=places`;
    script.async = true;
    document.head.appendChild(script);

    script.onload = () => {
      new google.maps.Map(
        document.getElementById("map") as HTMLElement,
        {
          center: { lat: 40.7831, lng: -73.9712 },
          zoom: 13,
        }
      );
    };
  }, []);

  return (
    <main style={{ height: "100vh" }}>
      <div id="map" style={{ height: "100%" }} />
    </main>
  );
}
