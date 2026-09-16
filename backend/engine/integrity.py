"""Integrity V0.3: only public, verifiable signals. Default INSUFFICIENT DATA."""

PUBLIC_WATCHLIST = [
    # Empty by default. Only populate with dated public investigations.
]


def assess(match: dict, news: list[dict] | None = None) -> dict:
    news = news or []
    hits = []
    blob = f"{match.get('home_team','')} {match.get('away_team','')} {match.get('competition','')}".lower()
    for item in PUBLIC_WATCHLIST:
        if item["needle"].lower() in blob:
            hits.append(item)
    for n in news:
        text = f"{n.get('title','')} {n.get('summary','')}".lower()
        if any(w in text for w in ("match-fixing investigation", "integrity investigation", "spot-fixing charge")):
            hits.append({"type": "public_report", "title": n.get("title")})

    if not hits:
        return {
            "level": "INSUFFICIENT DATA",
            "label": "INSUFFICIENT DATA",
            "note": "No publicly verifiable integrity investigation was attached to this match. Absence of evidence is not evidence of integrity problems, and this module does not claim the match is clean or fixed.",
        }
    return {
        "level": "MODERATE RISK",
        "label": "MODERATE RISK",
        "note": "Public integrity-related reporting exists. Not a determination that the match is fixed.",
        "signals": hits,
    }
