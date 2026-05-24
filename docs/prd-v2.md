# BrewDesk — V2 PRD

> **Status:** Draft · May 2026
> **Scope:** V2 = the first "showable" product + post-launch feature set. V1 was the inline-scraping prototype. The current technical build (pre-built DB, background crawler) is the V2 architecture — this PRD defines the **product** layer on top of it.

---

## Problem

NYC knowledge workers need a spot to work between meetings and currently get no useful signal from "coffee shop near me." Google Maps shows ratings and distance — not whether there's wifi, free outlets, or a noise level compatible with a video call. BrewDesk surfaces real WFH signal from Reddit, blogs, and Instagram, but the app today is unpolished, unbranded, and not shareable.

**V2 goal:** Ship a product someone could actually use and share — not just a working prototype.

---

## Target user

**Primary:** NYC-based hybrid/remote knowledge worker, frequently in-person meetings in Manhattan, needs a working spot for 1–3 hours between commitments.

**Their decision criteria (in order):**
1. Is it open right now?
2. Does it have wifi and outlets?
3. Is it quiet enough to take a call?
4. Is it actually close to where I am?

---

## Success metrics

| Metric | V2 target |
|--------|-----------|
| Someone can open the app cold and understand what it is in < 5 sec | Qualitative — passes with 3/3 test users |
| Clicking a pin shows useful info without a visible bug | Zero console errors in InfoCard flow |
| App works on mobile (iPhone Safari) | InfoCard renders correctly as bottom sheet |
| At least one place is found and acted on per session | Baseline to measure against in V3 |

---

## V2 scope

V2 ships in two phases:

- **Phase 1 — Showable:** Fix everything broken or misleading. Someone can open the app, understand it, and find a spot they'd go to.
- **Phase 2 — After launch:** Features that make the app genuinely useful beyond a demo.

---

## Phase 1: Showable

### Bugs (must fix — app is broken without these)

**BUG-1 · Pin colors don't reflect WFH score**
All pins are hardcoded red. The scoring system works but isn't reflected on the map — makes the map unreadable at a glance.
- Fix: green (`#22c55e`) for score ≥ 8.0, amber (`#f59e0b`) for ≥ 6.0
- File: `coffee-map/components/map/PlacePin.tsx`

**BUG-2 · Pins accumulate and disappear with every pan**
Viewport-based fetching means old pins never clear and new ones keep stacking. Should load all Manhattan places once on mount, not per-pan.
- Fix: one fetch on mount for all seeded places; keep pan-triggered nearby search for metadata enrichment only (photos, hours, rating) — don't use it to gate which pins show
- Files: `coffee-map/hooks/usePlaces.ts`, `/api/places/route.ts`

**BUG-3 · Every map render tears down and recreates all pins**
`handlePinClick` is recreated inline on every render → `PlacePin` useEffect dep fires → all `AdvancedMarkerElement`s remount. Visible flicker + API quota burn.
- Fix: `useCallback` on `handlePinClick` with `[places]` dep
- File: `coffee-map/components/map/MapContainer.tsx`

**BUG-7 · Photos don't render (API key IP restriction)**
Photo URLs are built with the server-side Google API key (IP-restricted to Render). Browser requests come from user IPs → 403.
- Fix: use `skipHttpRedirect=true` on Places Photo API to get a `googleusercontent.com` CDN URL instead; store it in Supabase once and return from cache
- File: `backend/services/google_places.py` — `_photo_urls()`

**BUG-8 · MentionCard shows "Mentioned this place" as fallback**
Generic fallback gives users no reason to trust the pin. Valid mentions without a WFH-specific snippet should show contextual fallback text instead (e.g., "Mentioned in a Reddit thread on r/nyc").
- Fix: `isUsefulSnippet()` guard + `buildFallback()` using platform + handle metadata
- File: `coffee-map/components/ui/MentionCard.tsx`

---

### UI & branding gaps (must fix — app is invisible without these)

**UI-1 · No visible app identity**
`page.tsx` is a full-screen map. A first-time visitor has no idea what BrewDesk is.
- Build: minimal sticky header (40–48px), blurred/transparent overlay — app name, tagline ("Find your next workspace between meetings"), optional "?" link

**UI-4 · No way to filter by open now**
Highest-value filter. Data is already in the payload (`regular_opening_hours.openNow`).
- Build: floating "Open Now" toggle chip; client-side filter — no backend call needed

---

### Should fix before sharing

**BUG-4 · Blank map during Render cold start**
Render free tier sleeps after inactivity; 30–60s wake time shows a silent blank map.
- Fix: expose `isLoading` from `usePlaces` → show a "Connecting…" pill during retry window

**BUG-5 · Geist font declared but not applied**
`--font-sans` set in theme but `body` hardcodes `Arial, Helvetica, sans-serif`.
- Fix: `font-family: var(--font-sans), sans-serif;` in `globals.css`

**BUG-6 · InfoCard shows stale place data after pan**
`selectedPlace` not cleared when bounds change — InfoCard shows pre-pan data.
- Fix: clear `selectedPlace` on `bounds_changed`, or re-find in fresh places list

**UI-5 · No loading state while fetching places**
`isLoading` tracked but never surfaced in the UI.
- Build: subtle loading pill or shimmer when `isLoading === true`

---

### Nice to have before sharing

**UI-2 · No map legend or onboarding context**
Users don't know what pin colors mean or how scores work.
- Build: small floating legend (bottom-right) — green/amber pin meaning + one-line score explanation

---

## Phase 2: Post-launch features

Prioritized by user impact. Build in this order after Phase 1 is stable.

### F-1 · Personalized score weighting _(high priority)_

**Why:** Different workers care about different things. A developer on calls needs quiet + wifi; a writer needs outlets and no time limit.

**What to build:**
- "What matters to you?" panel in the header — user picks one priority: Outlets / WiFi / Quiet / Laptop-friendly
- Frontend re-weights `wfh_score` formula locally and re-sorts visible pins — no backend call needed (all confidence scores are already in the `PlacePin` payload)
- Pin colors update immediately
- Preference persisted in `localStorage` — no login required

**Weights per preference:**
```ts
const WEIGHTS = {
  outlets:  { wifi: 1.5, outlet: 4.0, noise: 1.5, laptop: 3.0 },
  wifi:     { wifi: 4.0, outlet: 1.5, noise: 1.5, laptop: 3.0 },
  quiet:    { wifi: 1.5, outlet: 1.5, noise: 4.5, laptop: 2.5 },
  laptop:   { wifi: 2.0, outlet: 2.0, noise: 2.0, laptop: 4.0 },
}
```

**Effort:** M · No backend changes needed

---

### F-2 · Nominate a place _(medium priority)_

**Why:** Crawler coverage is good but not exhaustive. Letting users submit missing places gives the product a social hook and surfaces blind spots.

**What to build (MVP):**
- "Nominate a spot" button in header → modal: place name + optional note
- `POST /nominations` — validate via Google Places Text Search, write to `nominations` table
- Manual admin review → trigger targeted crawl via existing `place_resolver` + `llm_extractor`
- No auto-crawl yet

**Nominations table (new):**
```sql
CREATE TABLE nominations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  place_name TEXT NOT NULL,
  address TEXT,
  note TEXT,
  submitted_at TIMESTAMPTZ DEFAULT now(),
  status TEXT DEFAULT 'pending'  -- pending | accepted | rejected
);
```

**Effort:** M

---

### F-3 · Borough expansion: Brooklyn + Queens _(medium priority)_

**Why:** Many BrewDesk users live or work outside Manhattan — Brooklyn especially.

**What to build:**
- Uncomment Brooklyn/Queens rows in `supabase/seed/nyc_regions.sql`
- Add slugs to `ALLOWED_CITY_SLUGS` in `backend/crawler/orchestrator.py`
- Seed crawl using borough-specific query set (neighborhood names: Williamsburg, Park Slope, LIC, Astoria, etc.)

**Effort:** M (crawl queries need tuning; code changes are minimal)

---

### F-4 · Weekly re-crawl scheduler _(small)_

**Why:** Place data goes stale. Hours change. New mentions appear. Manual triggers don't scale.

**What to build:**
- APScheduler cron via `backend/background/scheduler.py` (already scaffolded)
- Re-crawl seeded regions weekly; only update places with new mentions (don't recompute for places with fresh `last_enriched_at`)

**Effort:** S

---

### F-5 · Map cluster markers _(medium priority)_

**Why:** With all Manhattan pins visible at once, zoom-out views become unreadable pin soup. Clustering is a standard map pattern for this.

**What to build:**
- `@googlemaps/markerclusterer` with `SuperClusterAlgorithm`
- Cluster bubble shows pin count; click zooms in
- Individual pins appear when zoom ≥ 15

**Effort:** M

---

### F-6 · Share a place _(small)_

**Why:** Easiest viral loop — "hey check out this spot" via direct link.

**What to build:**
- Deep link: `/?place_id=ChIJ...` opens the map centered on that pin with InfoCard pre-opened
- Share button in InfoCard copies link to clipboard
- OG meta tags with place name + score for link previews

**Effort:** S

---

### F-7 · Admin dashboard _(medium)_

**Why:** No visibility into crawl health, region status, or mention counts without hitting Supabase directly.

**What to build:**
- Password-protected `/admin` route (Next.js middleware, `X-Admin-Key` check)
- Region health table: slug, status, last_crawled_at, place count, mention count
- Manual "Trigger crawl" button per region
- Recent nominations queue with accept/reject actions

**Effort:** M

---

### F-8 · Score explanation tooltip _(small)_

**Why:** "8.4" means nothing to a new user. One line of context converts skeptics.

**What to build:**
- `?` icon next to `ScoreBadge`
- Tooltip: "Score based on [N] web mentions across [M] sources. Weighted by wifi, outlets, noise, and laptop-friendly signals."

**Effort:** S

---

## Out of scope for V2

These belong in V3 and should not be pulled into V2 scope:

- Authentication / user accounts / saved favorites
- Advanced filters (wifi, outlets, noise toggles) — wait until personalized scoring ships
- City expansion beyond NYC
- Monetization
- Native mobile app
- Full design system / brand refresh
- Social layer (check-ins, user reviews, "I'm here now")

---

## Open questions

1. **Borough expansion timing** — Brooklyn crawl is low-effort code-wise but needs query tuning for neighborhood coverage. Is there enough demand to justify before launch?
2. **Nominations moderation** — manual review is fine for early days. At what nomination volume does this need automation?
3. **Score transparency** — do users trust a score they can't explain? F-8 is small; should it ship in Phase 1?
4. **Mobile layout** — InfoCard as bottom sheet is the plan. Should V2 include a PWA config for "Add to Home Screen"?

---

*Source of truth: product-brief.md for current bug/UI inventory · v2-architecture-plan.md for technical decisions*
