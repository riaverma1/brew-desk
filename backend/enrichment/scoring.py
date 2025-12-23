from typing import Dict, List


def extract_signals(details: Dict) -> Dict:
    # Very basic heuristic v0: scan review text for keywords.
    reviews = details.get("reviews", []) or []
    text = " ".join([(rv.get("text") or "") for rv in reviews]).lower()

    wifi_hits = ["wifi", "wi-fi", "internet"]
    laptop_hits = ["laptop", "work", "working", "study", "studying", "remote", "wfh"]
    outlet_hits = ["outlet", "outlets", "plug", "plugs", "socket", "sockets", "charging"]
    noise_hits = ["quiet", "calm", "peaceful", "noisy", "loud", "crowded", "busy"]

    def count_hits(phrases: List[str]) -> int:
        return sum(text.count(p) for p in phrases)

    wifi = count_hits(wifi_hits)
    laptop = count_hits(laptop_hits)
    outlets = count_hits(outlet_hits)
    noise = count_hits(noise_hits)

    # crude scores
    wifi_score = min(1.0, wifi / 2.0)                 # 2+ mentions -> 1.0
    laptop_score = min(1.0, laptop / 3.0)             # 3+ mentions -> 1.0
    outlets_score = min(1.0, outlets / 2.0)

    # confidence: how much evidence you actually saw
    evidence_total = wifi + laptop + outlets
    confidence = "low"
    if evidence_total >= 5:
        confidence = "high"
    elif evidence_total >= 2:
        confidence = "medium"

    # numeric confidence for downstream derived schema consumers
    confidence_numeric = min(1.0, evidence_total / 5.0)

    # Evidence snippets: store a couple reviews that contain key terms
    evidence_reviews = []
    for rv in reviews:
        t = (rv.get("text") or "").lower()
        if any(k in t for k in ["wifi", "wi-fi", "laptop", "outlet", "work", "study"]):
            evidence_reviews.append({
                "author_name": rv.get("author_name"),
                "rating": rv.get("rating"),
                "relative_time_description": rv.get("relative_time_description"),
                "text": rv.get("text"),
            })
        if len(evidence_reviews) >= 3:
            break

    insights = []
    if wifi_score >= 0.5:
        insights.append("WiFi likely available")
    if outlets_score >= 0.5:
        insights.append("Some outlets mentioned")
    if laptop_score >= 0.5:
        insights.append("Laptop-friendly mentions")
    if not insights:
        insights.append("Insufficient evidence about work-friendliness")
    summary = "; ".join(insights)

    return {
        "wifi_score": wifi_score,
        "laptop_friendly_score": laptop_score,
        "outlets_score": outlets_score,
        "confidence": confidence,
        "confidence_numeric": confidence_numeric,
        "summary": summary,
        "keyword_counts": {
            "wifi": wifi,
            "laptop_work": laptop,
            "outlets": outlets,
            "noise_terms": noise,
        },
        "evidence_reviews": evidence_reviews,
    }
