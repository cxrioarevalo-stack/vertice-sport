import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import app  # noqa: E402


client = TestClient(app)


def test_health_keeps_predictive_model_disabled():
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["system"] == "VÉRTICE SPORT"
    assert payload["model_status"] == "NOT_READY"


def test_analysis_contract_does_not_expose_model_values_when_not_ready():
    response = client.get("/api/analysis")
    assert response.status_code == 200
    payload = response.json()
    assert payload["model_status"] == "NOT_READY"
    assert payload["model_probability"] is None
    assert payload["ev"] is None


def test_features_requires_match_id_without_touching_prediction_path():
    response = client.get("/api/features")
    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] == "match_id required"
    assert "future_slots" in payload
