
import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from pydantic import BaseModel, Field

from app.db.database import get_benchmark as get_saved_benchmark, list_benchmarks, save_benchmark
from app.services.llm_service import generate_response
from app.services.validation_service import validate_response

router = APIRouter(prefix="/api", tags=["Benchmark"])


class BenchmarkCase(BaseModel):
    prompt: str = Field(..., min_length=1)
    source_content: Optional[str] = None
    expected_schema: Optional[Dict[str, Any]] = None
    # Optional override for prompts whose JSON intent is ambiguous.
    # A supplied schema always means JSON is required.
    expects_json: Optional[bool] = None


class BenchmarkRequest(BaseModel):
    models: List[str] = Field(..., min_length=2, max_length=2)
    cases: List[BenchmarkCase] = Field(..., min_length=1, max_length=10)


def ensure_benchmark_table() -> None:
    """Compatibility helper; the shared DB initializer creates/migrates this table."""
    from app.db.database import initialize_database
    initialize_database()


def validate_expected_schema(schema: Dict[str, Any]) -> None:
    """Reject invalid JSON Schema definitions before model execution."""
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid expected JSON schema: {exc.message}",
        ) from exc


def check_schema(
    parsed_response: Any,
    expected_schema: Optional[Dict[str, Any]],
) -> Optional[bool]:
    """
    Return True or False when a schema is provided.
    Return None when no schema was supplied.
    """
    if expected_schema is None:
        return None

    try:
        Draft202012Validator(expected_schema).validate(parsed_response)
        return True
    except ValidationError:
        return False


def average_value(items: list, field: str) -> Optional[float]:
    """Calculate the mean of available numeric measurements."""
    values = [
        item[field]
        for item in items
        if isinstance(item.get(field), (int, float))
        and not isinstance(item.get(field), bool)
    ]

    if not values:
        return None

    return round(sum(values) / len(values), 2)


def reliability_percent(
    items: list,
    field: str,
) -> Optional[float]:
    """Calculate reliability only across measured boolean outcomes."""
    values = [
        item[field]
        for item in items
        if isinstance(item.get(field), bool)
    ]

    if not values:
        return None

    return round(
        100 * sum(value is True for value in values) / len(values),
        2,
    )


def expects_json_output(case: BenchmarkCase) -> bool:
    """Determine whether JSON syntax is part of the requested output contract.

    A schema is authoritative. Otherwise an explicit request field takes
    precedence over a conservative prompt-language heuristic.
    """
    if case.expected_schema is not None:
        return True
    if case.expects_json is not None:
        return case.expects_json

    prompt = case.prompt.strip().lower()
    patterns = (
        r"\b(?:return|output|provide|respond(?:\s+with)?|produce)\b.{0,100}\bjson\b",
        r"\bvalid\s+json\b",
        r"\bjson[- ]only\b",
        r"\bjson\s+(?:object|array|format|response)\b",
    )
    return any(re.search(pattern, prompt, flags=re.DOTALL) for pattern in patterns)


def build_benchmark_prompt(case: BenchmarkCase) -> str:
    """Include the source content in the prompt sent to the model."""
    prompt = case.prompt.strip()

    if case.source_content and case.source_content.strip():
        prompt += (
            "\n\nUse only the following source content as factual evidence. "
            "Do not invent or substitute company names, technologies, or "
            "numbers. If the source does not contain the requested "
            "information, represent that honestly in the requested output "
            "format.\n\n"
            f"SOURCE CONTENT:\n{case.source_content.strip()}"
        )

    if case.expected_schema is not None:
        prompt += (
            "\n\nReturn only valid JSON that conforms to this JSON Schema. "
            "Do not include Markdown fences or explanatory text.\n"
            f"JSON SCHEMA:\n{json.dumps(case.expected_schema)}"
        )

    return prompt


@router.post("/benchmark")
async def run_benchmark(request: BenchmarkRequest):
    """
    Run the same test cases against two different models.

    JSON syntax validity, schema validity, and validation outcomes
    are reported separately.
    """
    models = [model.strip() for model in request.models]

    if any(not model for model in models) or models[0] == models[1]:
        raise HTTPException(
            status_code=422,
            detail="Provide two different, non-empty model names.",
        )

    for case in request.cases:
        if case.expected_schema is not None:
            validate_expected_schema(case.expected_schema)

    run_id = str(uuid.uuid4())
    results = []

    for case_index, case in enumerate(request.cases, start=1):
        for model_name in models:
            start_time = time.perf_counter()

            try:
                benchmark_prompt = build_benchmark_prompt(case)

                response_text = await generate_response(
                    prompt=benchmark_prompt,
                    model=model_name,
                    expected_schema=case.expected_schema,
                )

                latency_ms = round(
                    (time.perf_counter() - start_time) * 1000,
                    2,
                )

                validation = validate_response(
                    response_text=response_text,
                    source_content=case.source_content,
                    expected_schema=case.expected_schema,
                )

                # JSON syntax validity is separate from schema validity.
                # Any JSON root type (object, array, string, number, boolean,
                # or null) is syntactically valid JSON.
                parsed_response = None
                json_valid = False
                try:
                    parsed_response = json.loads(response_text)
                    json_valid = True
                except (json.JSONDecodeError, TypeError):
                    parsed_response = None

                # Schema validity is unknown when no schema is supplied,
                # and false if the response is not valid JSON.
                if not json_valid:
                    schema_valid = (
                        False if case.expected_schema is not None
                        else None
                    )
                else:
                    schema_valid = check_schema(
                        parsed_response,
                        case.expected_schema,
                    )

                contradictions = list(validation.contradictions)
                # The validator's `hallucinations` field currently contains
                # validation issues and warnings, not only proven hallucinations.
                validation_issues = list(validation.hallucinations)

                evidence_findings = [
                    finding.model_dump()
                    for finding in validation.evidence_findings
                ]

                has_unsupported_claims = any(
                    finding.get("classification") == "unsupported"
                    for finding in evidence_findings
                )

                json_required = expects_json_output(case)
                source_available = bool(
                    isinstance(case.source_content, str)
                    and case.source_content.strip()
                )

                # Missing source content means grounding is unavailable, not
                # that the response is hallucinated. Keep that warning visible
                # but do not fail a general-knowledge response for it alone.
                no_source_warning = (
                    "Grounding could not be verified because no source content was provided."
                )
                validation_warnings = (
                    [no_source_warning]
                    if not source_available and no_source_warning in validation_issues
                    else []
                )
                # Do not label a missing-source warning as a hallucination.
                hallucinations = [
                    issue for issue in validation_issues
                    if issue not in validation_warnings
                ]
                blocking_issues = [
                    issue for issue in validation_issues
                    if issue not in validation_warnings
                ]

                # Conservative heuristic gate, not proof of factual correctness.
                validation_passed = (
                    (not json_required or json_valid)
                    and schema_valid is not False
                    and not contradictions
                    and not blocking_issues
                    and not has_unsupported_claims
                )

                results.append(
                    {
                        "case_index": case_index,
                        "model": model_name,
                        "response": response_text,
                        "quality_score": validation.quality_score,
                        "grounding_score": validation.grounding_score,
                        "completeness_score": (
                            validation.completeness_score
                        ),
                        "json_valid": json_valid,
                        "json_required": json_required,
                        "schema_valid": schema_valid,
                        "grounding_available": source_available,
                        "validation_warnings": validation_warnings,
                        "blocking_issues": blocking_issues,
                        "validation_passed": validation_passed,
                        "latency_ms": latency_ms,
                        "failure_type": (
                            "passed"
                            if validation_passed
                            else "quality_gate_failed"
                        ),
                        "evidence_findings": evidence_findings,
                        "contradictions": contradictions,
                        "hallucinations": hallucinations,
                        "recommended_actions": (
                            validation.recommended_actions
                        ),
                    }
                )

            except Exception as exc:
                latency_ms = round(
                    (time.perf_counter() - start_time) * 1000,
                    2,
                )

                results.append(
                    {
                        "case_index": case_index,
                        "model": model_name,
                        "response": None,
                        "quality_score": None,
                        "grounding_score": None,
                        "completeness_score": None,
                        "json_valid": False,
                        "json_required": expects_json_output(case),
                        "schema_valid": (
                            False
                            if case.expected_schema is not None
                            else None
                        ),
                        "grounding_available": bool(
                            isinstance(case.source_content, str)
                            and case.source_content.strip()
                        ),
                        "validation_warnings": [],
                        "blocking_issues": [str(exc)],
                        "validation_passed": False,
                        "latency_ms": latency_ms,
                        "failure_type": "execution_error",
                        "error": str(exc),
                        "evidence_findings": [],
                        "contradictions": [],
                        "hallucinations": [],
                        "recommended_actions": [],
                    }
                )

    summaries = []

    for model_name in models:
        model_results = [
            item for item in results
            if item["model"] == model_name
        ]

        successful = [
            item for item in model_results
            if item.get("response") is not None
        ]

        summaries.append(
            {
                "model": model_name,
                "cases_run": len(model_results),
                "successful_runs": len(successful),
                "average_quality_score": average_value(
                    successful, "quality_score"
                ),
                "average_grounding_score": average_value(
                    successful, "grounding_score"
                ),
                "average_completeness_score": average_value(
                    successful, "completeness_score"
                ),
                "average_latency_ms": average_value(
                    model_results, "latency_ms"
                ),
                "json_reliability_percent": reliability_percent(
                    [item for item in model_results if item.get("json_required") is True],
                    "json_valid",
                ),
                "schema_reliability_percent": reliability_percent(
                    model_results, "schema_valid"
                ),
                "validation_pass_rate_percent": reliability_percent(
                    model_results, "validation_passed"
                ),
            }
        )

    try:
        save_benchmark(run_id, models, len(request.cases), summaries, results)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save benchmark results: {exc}",
        ) from exc

    return {
        "run_id": run_id,
        "models": models,
        "cases_count": len(request.cases),
        "summaries": summaries,
        "results": results,
        "note": (
            "Measurements come from this run on this machine. "
            "JSON syntax validity is measured only for cases that require JSON; "
            "schema conformance and quality-gate outcomes are reported separately. "
            "When no source is provided, grounding is unavailable and that warning "
            "alone does not fail the gate. Unsupported claims are not automatically "
            "treated as false. The validation pass rate is heuristic and does not "
            "prove factual correctness. Cost comparisons require verified pricing "
            "and usage data."
        ),
    }


@router.get("/benchmarks")
def get_benchmark_history(limit: int = 20):
    """Return saved benchmark runs from SQLite, newest first."""
    ensure_benchmark_table()
    runs = list_benchmarks(limit=limit)
    return {"total": len(runs), "runs": runs}


@router.get("/benchmark/{run_id}")
def get_benchmark(run_id: str):
    """Retrieve a previously saved benchmark run, including summaries and case results."""
    ensure_benchmark_table()
    record = get_saved_benchmark(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    return record
