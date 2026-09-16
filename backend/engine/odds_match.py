from __future__ import annotations

import re
import unicodedata
from datetime import datetime

ALIASES = {
    "man utd": "manchester united",
    "man united": "manchester united",
    "manchester utd": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur",
    "newcastle": "newcastle united",
    "wolves": "wolverhampton wanderers",
    "nottm forest": "nottingham forest",
    "nottingham": "nottingham forest",
    "psg": "paris saint germain",
    "atletico": "atletico madrid",
    "atlético": "atletico madrid",
    "inter": "inter milan",
    "internazionale": "inter milan",
    "bayern": "bayern munich",
    "bayern munchen": "bayern munich",
}


def norm_name(name: str | None) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(fc|cf|afc|sc|ssc|ac|bk|fk|sk|cd|rc|ud|de|the)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return ALIASES.get(s, s)


def parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def match_event(bbc: dict, provider: dict, max_minutes: int = 180) -> tuple[bool, float, str]:
    h1, a1 = norm_name(bbc.get("home_team")), norm_name(bbc.get("away_team"))
    h2, a2 = norm_name(provider.get("home_team")), norm_name(provider.get("away_team"))
    if not h1 or not a1 or not h2 or not a2:
        return False, 0.0, "missing team name"
    if h1 == h2 and a1 == a2:
        score = 0.9
        reason = "exact home/away"
    elif h1 == a2 and a1 == h2:
        return False, 0.0, "home/away reversed — not attached"
    elif (h1 in h2 or h2 in h1) and (a1 in a2 or a2 in a1) and min(len(h1), len(h2), len(a1), len(a2)) >= 4:
        score = 0.75
        reason = "partial name match"
    else:
        return False, 0.0, "team names do not match"
    t1, t2 = parse_kickoff(bbc.get("kickoff_utc")), parse_kickoff(provider.get("kickoff_utc"))
    if t1 and t2:
        delta = abs((t1 - t2).total_seconds()) / 60
        if delta > max_minutes:
            return False, 0.0, f"kickoff differs by {int(delta)} minutes"
        if delta <= 15:
            score += 0.1
            reason += " + kickoff ±15m"
    else:
        score -= 0.15
        reason += " (kickoff missing)"
    if score < 0.8:
        return False, score, f"low confidence ({reason})"
    return True, min(score, 1.0), reason
