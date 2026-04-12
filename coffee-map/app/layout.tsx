import type { Metadata } from 'next'
import Script from 'next/script'
import './globals.css'

export const metadata: Metadata = {
  title: 'WFH Coffee Shop Finder',
  description: 'Find laptop-friendly coffee shops in NYC',
  manifest: '/manifest.webmanifest',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'default',
    title: 'Coffee Map',
  },
  icons: {
    apple: '/icons/apple-touch-icon.png',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const mapsApiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? ''

  return (
    <html lang="en">
      <head>
        {/* Load Maps JS API with libraries=marker for AdvancedMarkerElement */}
        <Script
          src={`https://maps.googleapis.com/maps/api/js?key=${mapsApiKey}&libraries=marker&v=beta`}
          strategy="beforeInteractive"
        />
      </head>
      <body className="antialiased">{children}</body>
    </html>
  )
}
