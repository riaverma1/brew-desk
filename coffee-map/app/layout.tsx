import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import Script from 'next/script'
import './globals.css'

const geistSans = Geist({ subsets: ['latin'], variable: '--font-geist-sans' })
const geistMono = Geist_Mono({ subsets: ['latin'], variable: '--font-geist-mono' })

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? 'https://brewdesk.vercel.app'

export const metadata: Metadata = {
  metadataBase: new URL(APP_URL),
  title: 'BrewDesk',
  description: 'Find your next workspace between meetings.',
  manifest: '/manifest.webmanifest',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'default',
    title: 'BrewDesk',
  },
  icons: {
    apple: '/icons/apple-touch-icon.png',
  },
  openGraph: {
    title: 'BrewDesk',
    description: 'Find your next workspace between meetings.',
    url: APP_URL,
    siteName: 'BrewDesk',

    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'BrewDesk',
    description: 'Find your next workspace between meetings.',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const mapsApiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? ''

  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
        <meta name="theme-color" content="#6f4e37" />
        {/* Load Maps JS API with libraries=marker for AdvancedMarkerElement */}
        <Script
          src={`https://maps.googleapis.com/maps/api/js?key=${mapsApiKey}&libraries=marker&v=beta`}
          strategy="afterInteractive"
        />
      </head>
      <body className="antialiased h-screen">{children}</body>
    </html>
  )
}
