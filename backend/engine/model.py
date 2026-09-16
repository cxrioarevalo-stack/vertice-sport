"""Model contract. No fake probabilities. Current runtime is NOT_READY."""
from __future__ import annotations

MODEL_VERSION = "baseline.logistic.v1.contract"
MODEL_NOT_READY = "NOT_READY"
MODEL_READY = "READY"
MODEL_TRAINED = "TRAINED"
MODEL_EVALUATED = "EVALUATED"


class BaselineModel:
    """Interpretable logistic-regression slot. Refuses to train without settled data."""

    def __init__(self):
        self.status = MODEL_NOT_READY
        self.version = MODEL_VERSION
        self.coefficients = None
        self.trained_at = None
        self.n_train = 0

    def train(self, observations: list[dict]) -> dict:
        settled = [o for o in observations if o.get("settlement_result") in ("WON", "LOST")]
        if len(settled) < 200:
            self.status = MODEL_NOT_READY
            self.coefficients = None
            self.n_train = 0
            return {
                "status": self.status,
                "trained": False,
                "reason": "insufficient_settled_observations",
                "n_settled": len(settled),
                "model_probability": None,
            }
        # Reserved for future fit. Never fabricate weights from odds-only rows.
        self.status = MODEL_NOT_READY
        return {
            "status": self.status,
            "trained": False,
            "reason": "training_disabled_until_readiness_gate",
            "n_settled": len(settled),
        }

    def predict(self, features: dict | None, market_context: dict | None = None) -> dict:
        return model_probability(features, market_context, model=self)


_DEFAULT = BaselineModel()


def model_status(model: BaselineModel | None = None) -> dict:
    m = model or _DEFAULT
    return {
        "model_status": m.status,
        "model_version": m.version,
        "model_probability": None,
        "trained_at": m.trained_at,
        "n_train": m.n_train,
        "coefficients": m.coefficients,
        "note": "Model remains NOT_READY until settled OddsPapi history meets readiness thresholds.",
    }


def model_probability(features: dict | None, market_context: dict | None = None,
                      model: BaselineModel | None = None) -> dict:
    m = model or _DEFAULT
    implied = None
    if market_context:
        implied = market_context.get("implied_probability")
    return {
        "model_status": m.status,
        "model_version": m.version,
        "model_probability": None if m.status == MODEL_NOT_READY else None,
        "market_implied_probability": implied,
        "market_implied_source": "MARKET" if implied is not None else None,
        "reason": "model_not_ready" if m.status == MODEL_NOT_READY else "no_trained_weights",
    }
