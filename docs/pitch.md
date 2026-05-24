# BrewDesk — Pitch

> *Find your next workspace between meetings.*

---

## The problem in one sentence

Google Maps will tell you there's a coffee shop nearby. It won't tell you if you can actually work there.

---

## What BrewDesk does

BrewDesk is a map of WFH-friendly spots in Manhattan where every pin is earned — not by Google ratings, but by real mentions from Reddit threads, blogs, and Instagram posts made by people who actually worked there.

Each pin has a WFH score (0–10) built from four signals: wifi reliability, outlet availability, noise level, and laptop-friendliness. You can see the actual sources that mentioned the place — the Reddit comment, the blog post, the Instagram caption — so you're not trusting an algorithm, you're trusting the community.

---

## Who it's for

NYC knowledge workers — designers, engineers, consultants, writers — who have a 2-hour gap between meetings and need somewhere to open a laptop that isn't their apartment. They know the problem intimately: every "cozy cafe" on Google Maps either has no outlets, kicks you out after 45 minutes, or plays music so loud you can't be on a call.

---

## Why BrewDesk, not X?

### vs. Google Maps
Google Maps is built for food decisions, not work decisions. Its reviews ask about the latte, not the wifi. It has no concept of outlets, noise, laptop-friendliness, or how long you can stay. You have to know what to search for. BrewDesk surfaces the right places automatically — and the signal comes from people who were explicitly there to work, not to eat.

### vs. NYC Cafe List / Eater / Timeout curated lists
Curated lists are snapshots. The cafe that was perfect in 2022 may have added "no laptops after noon" signage since then. BrewDesk's data is continuously crawled — new mentions from the web are picked up automatically, and scores update as new signal comes in. And unlike a list, it's on a map with a score, not a ranked article you have to cross-reference with your location.

### vs. Workfrom / WorkFrom.co
Workfrom is user-submitted. It requires people to opt in and report spots — which means coverage is sparse and uneven, concentrated in cities where tech workers were already talking about it in 2015. BrewDesk doesn't wait for user reports. The internet is already full of WFH discussions. We just mine them.

### vs. Yelp
Yelp's review prompts are built around dining: food quality, service, ambiance. Even if you find a review that mentions wifi, it's buried in 200 reviews about the eggs benedict. BrewDesk extracts specifically the signals that matter for working — and weights them into a single score you can act on at a glance.

---

## The core insight

People have been having the exact conversation BrewDesk is trying to answer for years — on Reddit, in travel blogs, in "best WFH spots near X" listicles. That information exists. It's just never been indexed, structured, and put on a map before.

BrewDesk is a data pipeline disguised as a map. The moat isn't the UI — it's the corpus of structured WFH signals extracted from unstructured public text, growing continuously.

---

## What's live today

- ~200+ WFH-verified spots in Manhattan, all with real web mentions as sources
- WFH score per place (wifi + outlets + noise + laptop-friendliness)
- Clickable pins that show the actual Reddit/blog/Instagram sources
- Open Now filter
- Real-time enrichment via Google Places (photos, hours, rating)
- Deployed on Vercel (frontend) + Render (backend) + Supabase (database)

---

## What's next

- Mobile-optimized layout (bottom sheet on tap)
- Personalized score weighting ("I care most about outlets" → pins re-rank)
- User nominations ("This place isn't on here yet")
- Brooklyn and Queens expansion
- Auth + saved favorites

---

## The ask / the conversation starter

*(Adjust for context — investor, user, collaborator)*

**For a user:** "Open it on your phone right now and tell me — is there a place near where your next meeting is that you'd actually go to?"

**For an investor / collaborator:** "The insight is that WFH discovery is a solved conversation — it's just scattered across the internet. We've built the pipeline to structure it. Manhattan is proof of concept. The question is how fast we can expand."

**For a press / media angle:** "Every coffee shop guide in New York is written by food journalists. This is the first one written by remote workers, for remote workers — and the data comes from them, not from us."

---

*BrewDesk — built May 2026*
