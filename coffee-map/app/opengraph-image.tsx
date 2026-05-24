import { ImageResponse } from 'next/og'

export const runtime = 'edge'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

export default function OgImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(135deg, #3b1f0e 0%, #6f4e37 50%, #a07850 100%)',
          fontFamily: 'sans-serif',
        }}
      >
        {/* Coffee cup icon */}
        <div style={{ fontSize: 96, marginBottom: 32 }}>☕</div>

        {/* App name */}
        <div
          style={{
            fontSize: 88,
            fontWeight: 700,
            color: '#fdf6ee',
            letterSpacing: '-2px',
            marginBottom: 20,
          }}
        >
          BrewDesk
        </div>

        {/* Tagline */}
        <div
          style={{
            fontSize: 32,
            color: '#d4a97a',
            letterSpacing: '0.5px',
            textAlign: 'center',
            maxWidth: 700,
          }}
        >
          Find your next workspace between meetings.
        </div>
      </div>
    ),
    { ...size }
  )
}
