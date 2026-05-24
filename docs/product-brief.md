# BrewDesk — Product Brief & Triage

> **Purpose of this doc:** Track what needs to get fixed, polished, and built to get BrewDesk to a "showable" state. Also captures the early thinking for v3. Use this as the source of truth for GitHub Issues.

---

## What the app is

**BrewDesk** — Find your next workspace between meetings.

A map that shows WFH-friendly coffee shops, cafes, and libraries in Manhattan. Every pin is backed by real web mentions (Reddit, blogs, Instagram) — not just Google ratings. Users can see wifi/outlets/noise level attributes and read the actual sources that mentioned the place.

**Target user:** NYC knowledge workers who need a spot to work between back-to-back meetings and want something better than "coffee shop near me."

---

## Current architecture (v2)

| Layer | Tech | Status |
|-------|------|--------|
| Frontend | Next.js 14, TypeScript, Tailwind, Google Maps JS | ✅ Deployed on Vercel |
| Backend | FastAPI, Python 3.11 | ✅ Deployed on Render (free tier) |
| Database | Supabase PostgreSQL | ✅ Live |
| Crawler | Tavily + Brave + Instagram → GPT-4o-mini → Supabase | ✅ Built, Manhattan seeded |
| Coverage | Manhattan only (other boroughs commented out) | 🔲 Phase 2 |

**How it works:** A background crawler pre-populates the DB with enriched places. When a user pans the map, the backend queries Supabase (~200ms, no LLM in the hot path). Pins only appear for places that have real web mentions.

---

## What "showable" means

The app is showable when someone can open it cold, understand what it is in 5 seconds, find a WFH spot they'd actually go to, and not hit a confusing or broken state. Concretely:

- [ ] Branding is visible — name, tagline, what the pins mean
- [ ] Pins show up with meaningful visual differentiation (not all the same color)
- [ ] Clicking a pin shows useful info without bugs
- [ ] Backend cold start doesn't leave the user staring at a blank map with no feedback
- [ ] No obvious JS bugs (pins re-mounting, accumulating, etc.)
- [ ] The app works on mobile (bottom sheet InfoCard renders correctly)

---

## Bugs (fix before showing anyone)

### 🔴 BUG-1: All map pins are red — score coloring not implemented
**File:** `coffee-map/components/map/PlacePin.tsx`

The architecture doc (and `ScoreBadge.tsx`) say pins should be green (score ≥ 8.0) and amber (score ≥ 6.0), but `PlacePin.tsx` hardcodes red (`#ef4444`) for every pin regardless of score. The scoring system exists and works — it's just not reflected on the map.

**Fix:** Use `place.wfh_score` to set `background` and `borderColor` on `PinElement`:
```ts
const color = place.wfh_score >= 8.0
  ? { bg: '#22c55e', border: '#15803d' }   // green
  : { bg: '#f59e0b', border: '#b45309' }   // amber
```
**Labels:** `bug`, `frontend`, `good first issue`

---

### 🔴 BUG-2: Show all pins globally, not just within the panned viewport
**File:** `coffee-map/hooks/usePlaces.ts`

**Desired behavior (updated):** Show ALL places from the DB on the map at once — not just ones in the current viewport. The map should behave like Google Maps: start centered on Manhattan, zoom to the user's current location when they grant permission, and have all WFH pins already visible. Users can then pan/zoom freely without pins appearing and disappearing.

The current behavior (viewport-based fetching on every pan) causes two problems:
1. Pins accumulate infinitely as the user pans — old pins from previous viewports stay on the map because they're never removed from the `places` state.
2. Pins feel unstable — they pop in and out depending on what's in the 1500m nearby search radius.

**Fix:** Load all places once on mount (or when the region is first seeded) and keep them. Stop the per-pan fetch loop for pin data. The Google Nearby Search call (which returns photos/rating/hours) should still run on pan to keep metadata fresh, but it shouldn't gate which pins appear.

Concretely:
- On mount, call `/api/places` once for the full Manhattan bounds to load all pins
- Keep the pan-triggered nearby search for metadata enrichment (photos, hours, rating) but don't use it to control which places are shown
- Geolocation: zoom to user's location exactly as it works now (green dot, pan + zoom to 14), but all pins are already on the map

**Labels:** `bug`, `frontend`, `ux`, `high priority`

---

### 🔴 BUG-3: PlacePin unmounts/remounts on every parent render
**File:** `coffee-map/components/map/MapContainer.tsx` + `coffee-map/components/map/PlacePin.tsx`

`handlePinClick` is defined inline in `MapContainer` and recreated on every render. `PlacePin`'s `useEffect` dep array includes `onClick`, so every render tears down and recreates every `AdvancedMarkerElement` on the map. This causes visible flicker and burns Google Maps API quota.

**Fix:** Wrap `handlePinClick` in `useCallback`:
```ts
const handlePinClick = useCallback((placeId: string) => {
  const place = places.find((p) => p.place_id === placeId) ?? null
  setSelectedPlace(place)
}, [places])
```
**Labels:** `bug`, `frontend`, `performance`

---

### 🟡 BUG-4: No UX for Render backend cold start
**File:** `coffee-map/lib/api-client.ts`

The Render free tier backend sleeps after inactivity and takes 30–60s to wake up. The retry logic handles 500s silently with exponential backoff, but the user sees a blank map with no feedback for up to ~30 seconds. There's no loading indicator, no "waking up" message, nothing.

**Fix:** Expose a loading/error state from `usePlaces` that the UI can use to show a "Connecting…" message during the retry window. Show the `CrawlingIndicator`-style pill when `isLoading` is true and places are empty.
**Labels:** `bug`, `ux`, `frontend`

---

### 🟡 BUG-5: Geist font declared but not applied
**File:** `coffee-map/app/globals.css`

`--font-sans` is set from the Geist font import in the theme, but `body` hardcodes `Arial, Helvetica, sans-serif`. The Geist font is imported in `layout.tsx` but never actually used anywhere.

**Fix:** Remove the hardcoded `font-family` from `body` in `globals.css` and use the CSS variable:
```css
body {
  font-family: var(--font-sans), sans-serif;
}
```
**Labels:** `bug`, `ui`, `good first issue`

---

### 🟡 BUG-6: Selected place not cleared when InfoCard closes on pan
**File:** `coffee-map/components/map/MapContainer.tsx`

If a user has an InfoCard open and pans the map, `selectedPlace` stays set even though the underlying data may have refreshed. The InfoCard shows stale data from before the pan. Should clear `selectedPlace` when bounds change (or re-find the place in the fresh list).
**Labels:** `bug`, `frontend`

---

### 🔴 BUG-7: Google Photos not rendering — API key embedded in photo URLs is IP-restricted
**File:** `backend/services/google_places.py` — `_photo_urls()` function

**Root cause (confirmed via git diff `e1ab8ed` → `832f372`):**

Photos are stored in Supabase correctly — the data is there. The problem is in how photo URLs are constructed. `_photo_urls()` builds URLs like:
```
https://places.googleapis.com/v1/places/{id}/photos/{ref}/media?maxHeightPx=600&maxWidthPx=800&key=SERVER_API_KEY
```
This URL embeds the **server-side Google API key** — the same key used by the FastAPI backend on Render, which is (per the README) IP-restricted to Render's outbound IP. When the browser tries to load `<img src={this_url}>`, the request comes from the **user's browser IP**, not Render's. Google rejects it with a 403, so no photo renders.

In V1 (older commits), the classic Google Places API used `photo_reference` strings that resolved to `maps.googleapis.com/maps/api/place/photo` URLs using the public browser key — those worked from any browser. The V2 rewrite switched to the new Places API and server key without accounting for this restriction.

**Fix — backend only, no frontend changes needed:**

Use `skipHttpRedirect=true` when fetching photo URLs. This makes the Places Photo API return a JSON response with a `photoUri` field containing an actual `googleusercontent.com` CDN URL — **no key embedded, no IP restrictions, works from any browser**.

Change `_photo_urls` from a sync helper into a coroutine (or call it in the background enrichment task):
```python
async def _resolve_photo_urls(place: dict, api_key: str, max_photos: int = 3) -> list[str]:
    photos = place.get("photos", [])[:max_photos]
    urls = []
    async with httpx.AsyncClient() as client:
        for photo in photos:
            name = photo.get("name", "")
            if not name:
                continue
            try:
                resp = await client.get(
                    f"https://places.googleapis.com/v1/{name}/media",
                    params={"maxHeightPx": 600, "maxWidthPx": 800,
                            "key": api_key, "skipHttpRedirect": "true"},
                    timeout=5,
                )
                uri = resp.json().get("photoUri", "")
                if uri:
                    urls.append(uri)
            except Exception:
                pass
    return urls
```

Store the resolved `googleusercontent.com` URLs in Supabase. These are stable (no expiry on typical CDN URLs), so re-fetching on every pan is unnecessary — just store them once and return from cache.

**Note:** This adds 1–3 sequential HTTP calls during the background enrichment step per place. Acceptable since it's already a background task. Don't call it in the hot path (nearby-search response).

**Labels:** `bug`, `backend`, `high priority`

---

### 🔴 BUG-8: MentionCard fallback text is too generic when no WFH quote exists
**File:** `coffee-map/components/ui/MentionCard.tsx`

**Important distinction:** A mention without a WFH-specific snippet is still a valid mention — a place listed in a "Top WFH spots near Flatiron" blog post is legitimate signal even if the source doesn't quote anything specific about the place. The mention count, source count, and wfh_score are all correct. Do NOT filter these out.

The problem is purely display: when `evidence_snippet` is null or is just the place name with no actual WFH context, the current fallback is the generic string `"Mentioned this place"` — which tells the user nothing useful. A user seeing that has no idea why this place is on the map.

**Fix — display-side only, no backend changes needed:**

In `MentionCard.tsx`, replace the generic fallback with a contextual one built from the source metadata already in the payload (`platform` + `handle_or_domain`). The fallback must catch all degenerate cases: `null`, empty string `""`, whitespace-only, a string that's just the place name, or the literal text `"Mentioned this place"` (which has been seen as an LLM-generated fallback).

```ts
const WFH_KEYWORDS = ['wifi', 'outlet', 'plug', 'noise', 'quiet', 'loud',
  'laptop', 'work', 'workspace', 'seat', 'power', 'hour']

function isUsefulSnippet(s: string | null | undefined, placeName: string): boolean {
  if (!s || !s.trim()) return false
  const lower = s.toLowerCase().trim()
  // Reject known bad patterns
  if (lower === 'mentioned this place') return false
  if (lower === placeName.toLowerCase().trim()) return false
  if (lower.length < 15) return false  // too short to be a real quote
  // Bonus: ideally contains a WFH signal, but don't require it —
  // a real quote is still better than a fallback even if it's about ambiance
  return true
}

function buildFallback(mention: MentionCardType): string {
  const source = mention.handle_or_domain
  switch (mention.platform) {
    case 'reddit':    return `Mentioned in a Reddit thread on r/${source}`
    case 'instagram': return `Featured by @${source} on Instagram`
    case 'blog':      return `Listed on ${source}`
    case 'tiktok':    return `Featured by @${source} on TikTok`
    default:          return `Mentioned on ${source}`
  }
}

// In MentionCard render:
const snippet = isUsefulSnippet(mention.evidence_snippet, place.name)
  ? mention.evidence_snippet!
  : buildFallback(mention)
```

Note: `MentionCard` currently doesn't receive `place.name` as a prop — either pass it down from `InfoCard`, or just check the first three bad patterns without the name comparison as a first pass.

**Labels:** `bug`, `ux`, `frontend`, `good first issue`

---

## UI & Branding gaps (fix before showing anyone)

### 🎨 UI-1: No visible branding or identity
`page.tsx` is just a full-screen map — no header, no logo, no app name visible, no tagline. A first-time visitor has no idea what "BrewDesk" is or what they're looking at. This is the most important thing to fix before showing the app to anyone.

**What to build:** A minimal sticky header (40–48px) with the app name, a one-line tagline ("Find your next workspace between meetings"), and optionally a "?" or "About" link. Should be transparent/blurred over the map, not a solid block.
**Labels:** `ui`, `branding`, `high priority`

---

### 🎨 UI-2: No map legend or onboarding context
There's no explanation of what the pins mean, what the score is, or why this app exists vs. just using Google Maps. Users who find it through a link have no context.

**What to build:** A small floating legend (bottom-left or bottom-right) explaining pin colors and the score. A first-visit tooltip or empty state message explaining the concept.
**Labels:** `ui`, `onboarding`

---

### 🎨 UI-3: InfoCard has no branding and looks generic
The side panel is clean and functional but completely unbranded. The `ScoreBadge` is the only distinctive element. The overall visual feel is "developer prototype."

**What to improve:** Custom typography, a subtle brand color accent, better spacing. Nothing major — just enough to feel intentional.
**Labels:** `ui`, `polish`

---

### 🎨 UI-4: "Open Now" toggle — the only filter for now
Users want to know if a place is actually open before heading there. The `openNow` boolean is already returned from the Google Nearby Search response inside `regular_opening_hours.openNow` and is present on the `PlacePin` type.

**What to build:** A single "Open Now" toggle chip — minimal, floating at the top of the map. When active, client-side filter the already-fetched places array to only show pins where `place.regular_opening_hours?.openNow === true`. No backend call needed.

No other filters for now (wifi, outlets, noise) — keeping it simple until the core experience is solid.

**Labels:** `feature`, `ui`, `now`

---

### 🎨 UI-5: No loading state while fetching places
`isLoading` from `usePlaces` is tracked but never shown in the UI. When the map loads or after a pan, there's no visual feedback that data is being fetched.

**What to build:** A subtle loading pill or shimmer that appears while `isLoading === true`.
**Labels:** `ui`, `ux`, `good first issue`

---

## Feature backlog (v2 — after showable)

| # | Feature | Why | Effort |
|---|---------|-----|--------|
| # | Feature | Why | Effort |
|---|---------|-----|--------|
| F-1 | **Personalized score weighting** | Let users say what they care about (outlets > noise, etc.) and re-rank pins accordingly | M |
| F-2 | **Nominate a place** | Let users submit a place to be crawled and added to the map | M |
| F-3 | Borough expansion (Brooklyn, Queens) | Remove Manhattan-only limitation | M |
| F-4 | Weekly re-crawl scheduler | Keep data fresh without manual triggers | S |
| F-5 | Map cluster markers | At zoom-out with all pins visible globally, clustering becomes important | M |
| F-6 | Share a place | Deep-link to a specific pin / place | S |
| F-7 | Admin dashboard | See crawl status, region health, mention counts | M |
| F-8 | Score explanation tooltip | Users don't know what "8.4" means | S |
| F-9 | Advanced filters (wifi, outlets, noise) | After personalized scoring ships, these are redundant for most users | L |

### F-2 Design notes: Personalized score weighting

The current `wfh_score` formula is fixed (wifi × 2.5, outlets × 2.0, noise × 2.0, laptop × 3.5). Not everyone weights these the same — a developer on a video call cares most about quiet and wifi; a writer with a laptop cares most about outlets and not being time-limited.

**Proposed approach (client-side, no auth required):**
- Add a "What matters to you?" panel (accessible from the header or a settings icon)
- User picks their top priority: Outlets / WiFi / Quiet / Laptop-friendly
- The frontend re-weights the score formula locally and re-sorts pins in the current viewport — no backend call needed since all confidence scores are already in the `PlacePin` payload
- Preference stored in `localStorage` — persists across sessions without login

**Score formula per preference:**
```ts
const WEIGHTS = {
  outlets:  { wifi: 1.5, outlet: 4.0, noise: 1.5, laptop: 3.0 },
  wifi:     { wifi: 4.0, outlet: 1.5, noise: 1.5, laptop: 3.0 },
  quiet:    { wifi: 1.5, outlet: 1.5, noise: 4.5, laptop: 2.5 },
  laptop:   { wifi: 2.0, outlet: 2.0, noise: 2.0, laptop: 4.0 },
}
```
Pin colors update accordingly. This is the highest-impact personalization feature and doesn't require any backend changes.

**Labels:** `feature`, `frontend`, `personalization`

---

### F-3 Design notes: Nominate a place

Let users submit a place that isn't on the map yet — either because it was never mentioned in web sources, or because the crawler missed it.

**User flow:**
1. User clicks "Nominate a spot" (button in header or floating action button)
2. Simple modal: type the place name + address, optional note ("it has great outlets but isn't on here")
3. Submission goes to a `nominations` table in Supabase
4. Backend: a new `POST /nominations` endpoint that validates the place exists via Google Places Text Search, then writes to the DB
5. Admin review (you) triggers a targeted crawl for nominated places via the existing `place_resolver` + `llm_extractor` pipeline
6. If enough WFH signal is found, the place gets added to `places` and shows up on the map

**MVP scope:** Just capture the nomination (name + address + optional note). No auto-crawl yet — review manually and trigger via the existing admin endpoint. Later: auto-crawl on nomination if confidence is high.

**Why it matters:** Social proof + community-sourced data is a core differentiator. Lets early users feel ownership of the map. Also surfaces places the crawler missed.

**Labels:** `feature`, `frontend`, `backend`, `community`

---

## v3 PRD notes (early thinking — not for now)

These are the questions to answer when it's time to spec v3. Don't build toward this yet — finish v2 first and learn from real users.

**Core questions:**
- Should the app expand beyond NYC? If so, how does seeding work at scale?
- Is the map the right primary interface, or should there be a list/search view?
- Who is the real target user — remote workers, travelers, freelancers?
- What does "good for working" mean beyond wifi/outlets? (Hours, crowding, vibe?)
- Is there a social layer — user-submitted reviews, "I'm here now"?
- What's the monetization angle, if any? (Affiliate links? Premium features?)

**Things to rebuild in v3:**
- Full brand/visual identity (not bootstrapped Tailwind)
- Proper design system
- Authentication (save favorite spots, history)
- Better data pipeline (more sources, higher coverage)
- City expansion strategy

---

## Priority order for "showable"

Work in this order:

**Must-fix (app is broken or misleading without these):**
1. **BUG-2** — All pins show globally, zoom to user location on load
2. **BUG-3** — Fix pin re-mounting (performance + visual flicker)
3. **BUG-7** — Google Photos (fix `skipHttpRedirect` to get real CDN URLs)
4. **BUG-8** — MentionCard fallback catches all bad snippet cases
5. **BUG-1** — Score-based pin colors (green/amber — makes the map readable at a glance)
6. **UI-1** — App header with name + tagline (zero identity right now)
7. **UI-4** — "Open Now" toggle (the only filter — high user value, data is already there)

**Should-fix before sharing:**
8. **BUG-4** — Backend cold start UX (don't leave users staring at a blank map)
9. **BUG-5** — Fix Geist font
10. **UI-5** — Loading state while fetching places
11. **BUG-6** — Clear selected place on pan

**Nice to have before showing:**
12. **UI-2** — Map legend / what do the pins mean?

**Post-showable features (build after first real demo):**
13. **F-1** — Personalized score weighting
14. **F-2** — Nominate a place

---

*Last updated: May 2026. Source of truth for GitHub Issues.*
