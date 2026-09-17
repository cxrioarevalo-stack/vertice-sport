"""Integrity V0.3: only public, verifiable signals. Default INSUFFICIENT DATA."""

PUBLIC_WATCHLIST = [
    # Empty by default. Only populate with dated public investigations.
]


def assess(match: dict, news: list[dict] | None = None) -> dict:
    """Assess publicly reported integrity signals without inferring guilt.

    The input is defensive: malformed news items are ignored, and duplicate
    signals are not repeated in the response.
    """
    news = news or []
    hits = []
    seen: set[tuple[str, str]] = set()
    blob = f"{match.get('home_team', '')} {match.get('away_team', '')} {match.get('competition', '')}".lower()

    def add_hit(item: dict) -> None:
        key = (str(item.get("type", "")), str(item.get("title", "")))
        if key not in seen:
            seen.add(key)
            hits.append(item)

    for item in PUBLIC_WATCHLIST:
        if item.get("needle", "").lower() in blob:
            add_hit(item)

    for item in news:
        if not isinstance(item, dict):
            continue
        text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if any(word in text for word in ("match-fixing investigation", "integrity investigation", "spot-fixing charge")):
            add_hit({"type": "public_report", "title": item.get("title")})

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
