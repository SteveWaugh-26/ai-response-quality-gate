"""API regression tests for AI Response Quality Gate.

Run from the project root:
    python -m pip install -r requirements.txt pytest
    python -m pytest -q

These tests mock Ollama and do not require a running local model.
"""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import database
from app.routers import benchmark as benchmark_router


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Use an isolated SQLite database for every test."""
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def fake_validation(
    *, quality_score=95.0, grounding_score=100.0, completeness_score=100.0,
    contradictions=None, hallucinations=None, evidence_findings=None,
    recommended_actions=None,
):
    """Build the validation-result shape used by the benchmark route."""
    return SimpleNamespace(
        quality_score=quality_score,
        grounding_score=grounding_score,
        completeness_score=completeness_score,
        contradictions=contradictions or [],
        hallucinations=hallucinations or [],
        evidence_findings=evidence_findings or [],
        recommended_actions=recommended_actions or [],
    )


def test_home_and_health(client):
    home = client.get("/")
    health = client.get("/health")
    assert home.status_code == 200
    assert home.json()["docs"] == "/docs"
    assert health.status_code == 200
    assert health.json() == {"status": "healthy"}


def test_failures_endpoint_returns_empty_list_when_no_failures(client):
    response = client.get("/api/failures")
    assert response.status_code == 200
    assert response.json() == {"total": 0, "failures": []}


def test_failures_endpoint_rejects_invalid_limit(client):
    assert client.get("/api/failures?limit=0").status_code == 422
    assert client.get("/api/failures?limit=501").status_code == 422


def test_benchmark_requires_two_distinct_model_names(client):
    response = client.post("/api/benchmark", json={
        "models": ["llama3.2:3b", "llama3.2:3b"],
        "cases": [{"prompt": "Return a short greeting."}],
    })
    assert response.status_code == 422
    assert "two different" in response.json()["detail"]


def test_benchmark_rejects_invalid_json_schema_before_model_call(client, monkeypatch):
    async def should_not_run(**kwargs):
        pytest.fail("Ollama should not be called for an invalid schema")
    monkeypatch.setattr(benchmark_router, "generate_response", should_not_run)
    response = client.post("/api/benchmark", json={
        "models": ["qwen3:4b", "llama3.2:3b"],
        "cases": [{"prompt": "Return JSON.",
                   "expected_schema": {"type": "not-a-real-json-schema-type"}}],
    })
    assert response.status_code == 422
    assert "Invalid expected JSON schema" in response.json()["detail"]


def test_benchmark_runs_both_models_and_saves_history(client, monkeypatch):
    async def fake_generate_response(prompt, model=None, expected_schema=None):
        return json.dumps({"message": f"hello from {model}"})
    monkeypatch.setattr(benchmark_router, "generate_response", fake_generate_response)
    monkeypatch.setattr(benchmark_router, "validate_response",
                        lambda **kwargs: fake_validation())
    response = client.post("/api/benchmark", json={
        "models": ["qwen3:4b", "llama3.2:3b"],
        "cases": [{"prompt": "Return a JSON object with a message field."}],
    })
    assert response.status_code == 200
    body = response.json()
    assert body["cases_count"] == 1
    assert len(body["results"]) == 2
    assert {item["model"] for item in body["results"]} == {"qwen3:4b", "llama3.2:3b"}
    assert all(item["json_valid"] is True for item in body["results"])
    assert all(item["schema_valid"] is None for item in body["results"])
    assert all(item["validation_passed"] is True for item in body["results"])
    history = client.get("/api/benchmarks")
    assert history.status_code == 200
    assert history.json()["total"] == 1
    run_id = body["run_id"]
    saved_run = client.get(f"/api/benchmark/{run_id}")
    assert saved_run.status_code == 200
    assert saved_run.json()["run_id"] == run_id
    assert len(saved_run.json()["results"]) == 2


def test_benchmark_marks_unsupported_claim_as_quality_gate_failure(client, monkeypatch):
    unsupported = SimpleNamespace(
        classification="unsupported",
        model_dump=lambda: {
            "claim": "approval_code is FAKE-APPROVAL-999",
            "classification": "unsupported", "evidence": "",
            "explanation": "The source does not provide an approval code.",
        },
    )
    async def fake_generate_response(prompt, model=None, expected_schema=None):
        return json.dumps({"approval_code": "FAKE-APPROVAL-999"})
    monkeypatch.setattr(benchmark_router, "generate_response", fake_generate_response)
    monkeypatch.setattr(benchmark_router, "validate_response",
                        lambda **kwargs: fake_validation(
                            grounding_score=50.0, evidence_findings=[unsupported]))
    response = client.post("/api/benchmark", json={
        "models": ["qwen3:4b", "llama3.2:3b"],
        "cases": [{"prompt": "Return the approval code as JSON.",
                   "source_content": "BluePeak Systems has exactly 42 employees."}],
    })
    assert response.status_code == 200
    for result in response.json()["results"]:
        assert result["validation_passed"] is False
        assert result["failure_type"] == "quality_gate_failed"
        assert any(f["classification"] == "unsupported" for f in result["evidence_findings"])


def test_benchmark_schema_validation_is_reported_separately(client, monkeypatch):
    async def fake_generate_response(prompt, model=None, expected_schema=None):
        return json.dumps({"name": "Ada"})  # valid JSON, but missing required age
    monkeypatch.setattr(benchmark_router, "generate_response", fake_generate_response)
    monkeypatch.setattr(benchmark_router, "validate_response",
                        lambda **kwargs: fake_validation())
    response = client.post("/api/benchmark", json={
        "models": ["qwen3:4b", "llama3.2:3b"],
        "cases": [{"prompt": "Return a JSON object.", "expected_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"], "additionalProperties": False,
        }}],
    })
    assert response.status_code == 200
    for result in response.json()["results"]:
        assert result["json_valid"] is True
        assert result["schema_valid"] is False
        assert result["validation_passed"] is False


# End-to-end execution recovery tests; the LLM is mocked.
from app.models import ValidationResult
from app.routers import execution as execution_router


def make_validation():
    return ValidationResult(
        quality_score=100,
        grounding_score=100,
        completeness_score=100,
    )


def test_execute_accepts_valid_response_and_persists_trace(client, monkeypatch):
    calls = []

    async def fake_generate_response(prompt, model=None, expected_schema=None):
        calls.append(model)
        return '{"employee_count": 150}'

    monkeypatch.setattr(execution_router, "generate_response", fake_generate_response)
    monkeypatch.setattr(
        execution_router, "_validate",
        lambda text, request: (make_validation(), "no_failure"),
    )

    response = client.post("/api/execute", json={
        "prompt": "Return the employee count as JSON.",
        "model": "llama3.2:3b",
        "max_retries": 2,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["retry_count"] == 0
    assert body["fallback_model_used"] is False
    assert body["original_response"] == '{"employee_count": 150}'
    assert body["final_response"] == body["original_response"]
    assert calls == ["llama3.2:3b"]
    assert any("passed" in item.lower() for item in body["execution_trace"])

    saved = client.get(f"/api/execution/{body['execution_id']}")
    assert saved.status_code == 200
    assert saved.json()["execution_id"] == body["execution_id"]


def test_execute_retries_and_accepts_repaired_response(client, monkeypatch):
    responses = iter([
        '{"employee_count": 200}',
        '{"employee_count": 150}',
    ])
    calls = []

    async def fake_generate_response(prompt, model=None, expected_schema=None):
        calls.append(prompt)
        return next(responses)

    validations = iter([
        (make_validation(), "possible_hallucination"),
        (make_validation(), "no_failure"),
    ])

    monkeypatch.setattr(execution_router, "generate_response", fake_generate_response)
    monkeypatch.setattr(
        execution_router, "_validate",
        lambda text, request: next(validations),
    )

    response = client.post("/api/execute", json={
        "prompt": "Return the employee count as JSON.",
        "source_content": "The company has 150 employees.",
        "model": "llama3.2:3b",
        "max_retries": 2,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["retry_count"] == 1
    assert body["original_response"] == '{"employee_count": 200}'
    assert body["final_response"] == '{"employee_count": 150}'
    assert len(calls) == 2
    assert any("repair/prompt correction" in item.lower()
               for item in body["execution_trace"])


def test_execute_uses_fallback_after_primary_validation_failure(client, monkeypatch):
    calls = []

    async def fake_generate_response(prompt, model=None, expected_schema=None):
        calls.append(model)
        if model == "llama3.2:3b":
            return '{"employee_count": 200}'
        return '{"employee_count": 150}'

    def fake_validate(text, request):
        if '"200"' in text or '"employee_count": 200' in text:
            return make_validation(), "possible_hallucination"
        return make_validation(), "no_failure"

    monkeypatch.setattr(execution_router, "generate_response", fake_generate_response)
    monkeypatch.setattr(execution_router, "_validate", fake_validate)

    response = client.post("/api/execute", json={
        "prompt": "Return the employee count as JSON.",
        "source_content": "The company has 150 employees.",
        "model": "llama3.2:3b",
        "fallback_model": "qwen3:4b",
        "max_retries": 0,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["fallback_model_used"] is True
    assert body["model_used"] == "qwen3:4b"
    assert body["final_response"] == '{"employee_count": 150}'
    assert calls == ["llama3.2:3b", "qwen3:4b"]
    assert any("Fallback response passed validation" in item
               for item in body["execution_trace"])


def test_execute_stops_at_maximum_retries(client, monkeypatch):
    calls = []

    async def fake_generate_response(prompt, model=None, expected_schema=None):
        calls.append(model)
        return '{"employee_count": 200}'

    monkeypatch.setattr(execution_router, "generate_response", fake_generate_response)
    monkeypatch.setattr(
        execution_router, "_validate",
        lambda text, request: (make_validation(), "possible_hallucination"),
    )

    response = client.post("/api/execute", json={
        "prompt": "Return the employee count as JSON.",
        "source_content": "The company has 150 employees.",
        "model": "llama3.2:3b",
        "max_retries": 2,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_review"
    assert body["retry_count"] == 2
    assert len(calls) == 3
    assert body["fallback_model_used"] is False
    assert any("Maximum primary-model retry count reached" in item
               for item in body["execution_trace"])


def test_execute_retains_primary_result_when_fallback_fails_validation(client, monkeypatch):
    calls = []

    async def fake_generate_response(prompt, model=None, expected_schema=None):
        calls.append(model)
        if model == "llama3.2:3b":
            return '{"employee_count": 200}'
        return '{"employee_count": 999}'

    def fake_validate(text, request):
        if '"employee_count": 999' in text:
            return make_validation(), "possible_hallucination"
        return make_validation(), "possible_hallucination"

    monkeypatch.setattr(
        execution_router, "generate_response", fake_generate_response
    )
    monkeypatch.setattr(execution_router, "_validate", fake_validate)

    response = client.post("/api/execute", json={
        "prompt": "Return the employee count as JSON.",
        "source_content": "The company has 150 employees.",
        "model": "llama3.2:3b",
        "fallback_model": "qwen3:4b",
        "max_retries": 0,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_review"
    assert body["fallback_model_used"] is False
    assert body["model_used"] == "llama3.2:3b"
    assert body["original_response"] == '{"employee_count": 200}'
    assert body["final_response"] == '{"employee_count": 200}'
    assert calls == ["llama3.2:3b", "qwen3:4b"]
    assert any(
        "Fallback response did not pass validation" in item
        for item in body["execution_trace"]
    )


def test_execute_persists_trace_without_premature_save_confirmation(client, monkeypatch):
    async def fake_generate_response(prompt, model=None, expected_schema=None):
        return '{"message": "verified test response"}'

    monkeypatch.setattr(
        execution_router, "generate_response", fake_generate_response
    )
    monkeypatch.setattr(
        execution_router,
        "_validate",
        lambda text, request: (make_validation(), "no_failure"),
    )

    response = client.post("/api/execute", json={
        "prompt": "Return a short JSON message.",
        "model": "llama3.2:3b",
        "max_retries": 0,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert "Execution record saved to SQLite." in body["execution_trace"]

    saved_response = client.get(f"/api/execution/{body['execution_id']}")
    assert saved_response.status_code == 200
    saved = saved_response.json()

    assert saved["execution_id"] == body["execution_id"]
    assert saved["final_response"] == '{"message": "verified test response"}'
    assert "Saving execution record to SQLite." in saved["execution_trace"]
    assert "Execution record saved to SQLite." not in saved["execution_trace"]
