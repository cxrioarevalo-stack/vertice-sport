"""Chronological train/validation/test split. Never shuffle time."""
from __future__ import annotations

from engine.odds_match import parse_kickoff


def _ts(row: dict):
    return parse_kickoff(row.get("as_of_utc") or row.get("observed_at") or row.get("kickoff_utc"))


def chronological_split(observations: list[dict], train_frac=0.6, val_frac=0.2) -> dict:
    settled = [o for o in observations if o.get("settlement_result") in ("WON", "LOST")]
    dated = [o for o in settled if _ts(o)]
    dated.sort(key=_ts)
    n = len(dated)
    if n < 30:
        return {
            "status": "NOT_READY",
            "reason": "insufficient_settled_dated_observations",
            "n": n,
            "train": [],
            "validation": [],
            "test": [],
            "random_split": False,
        }
    i_train = max(1, int(n * train_frac))
    i_val = max(i_train + 1, int(n * (train_frac + val_frac)))
    return {
        "status": "READY",
        "reason": None,
        "n": n,
        "train": dated[:i_train],
        "validation": dated[i_train:i_val],
        "test": dated[i_val:],
        "random_split": False,
        "method": "chronological",
    }


def assert_no_future_leak(train: list[dict], later: list[dict]) -> bool:
    tmax = [_ts(o) for o in train if _ts(o)]
    if not tmax:
        return True
    last = max(tmax)
    return all((_ts(o) or last) >= last for o in later) or all(
        _ts(o) is None or _ts(o) >= last for o in later
    )
