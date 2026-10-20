
import json

from app.services.validation_service import (
    _value_is_supported,
    detect_numeric_contradiction,
    extract_evidence_findings,
    extract_numbers,
    normalize_words,
    parse_response_claims,
    validate_response,
)


def test_normalize_words_handles_case_and_numbers():
    words = normalize_words("Python 3.10 is used by 42 teams.")
    assert "python" in words
    assert "3.10" in words
    assert "42" in words


def test_extract_numbers_handles_negative_decimal_and_percentage():
    assert extract_numbers("Values: -4, 3.5 and 20%") == {
        "-4", "3.5", "20%"
    }


def test_parse_plain_text_into_claims():
    assert parse_response_claims(
        "Python is useful. FastAPI is a framework."
    ) == [
        "Python is useful.",
        "FastAPI is a framework.",
    ]


def test_parse_json_keeps_field_context():
    claims = parse_response_claims(
        json.dumps({
            "company_name": "BluePeak Systems",
            "employee_count": 42,
        })
    )

    assert "company name: BluePeak Systems" in claims
    assert "employee count: 42" in claims


def test_company_name_is_supported_by_source():
    findings = extract_evidence_findings(
        '{"company_name":"BluePeak Systems"}',
        "BluePeak Systems has exactly 42 employees.",
    )

    assert len(findings) == 1
    assert findings[0].classification == "supported"


def test_company_name_not_in_source_is_unsupported():
    findings = extract_evidence_findings(
        '{"company_name": "UnknownTech Solutions"}',
        "BluePeak Systems develops software.",
    )

    assert len(findings) == 1
    assert findings[0].classification == "unsupported"


def test_missing_approval_code_is_unsupported_not_proven_false():
    findings = extract_evidence_findings(
        '{"approval_code":"FAKE-APPROVAL-999"}',
        "BluePeak Systems has exactly 42 employees.",
    )

    assert len(findings) == 1
    assert findings[0].classification == "unsupported"
    assert (
        "does not necessarily mean false"
        in findings[0].explanation.lower()
    )


def test_explicit_abstention_is_classified_separately():
    findings = extract_evidence_findings(
        '{"approval_code":"not provided"}',
        "BluePeak Systems has exactly 42 employees.",
    )

    assert len(findings) == 1
    assert findings[0].classification == "abstained"


def test_numeric_contradiction_checks_relevant_context():
    assert detect_numeric_contradiction(
        "BluePeak Systems employee_count: 43",
        "BluePeak Systems has exactly 42 employees.",
        "BluePeak Systems has exactly 42 employees.",
    )

    assert not detect_numeric_contradiction(
        "launch_year: 2027",
        "BluePeak Systems has exactly 42 employees.",
        "BluePeak Systems has exactly 42 employees.",
    )


def test_validate_response_reports_unsupported_claim_in_issues():
    result = validate_response(
        response_text=(
            '{"company_name":"BluePeak Systems",'
            '"approval_code":"FAKE-APPROVAL-999"}'
        ),
        source_content="BluePeak Systems has exactly 42 employees.",
    )

    assert any(
        "Unsupported claim" in issue
        for issue in result.hallucinations
    )
    assert any(
        finding.classification == "unsupported"
        for finding in result.evidence_findings
    )
    assert result.grounding_score < 100


def test_valid_json_can_fail_schema_validation():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
        "required": ["name", "age"],
        "additionalProperties": False,
    }

    result = validate_response(
        '{"name":"Ada"}',
        "The person's name is Ada.",
        schema,
    )

    assert result.completeness_score == 50.0
    assert result.quality_score <= 25.0
    assert any(
        "JSON/schema validation failed" in issue
        for issue in result.hallucinations
    )


def test_empty_response_is_zero_score_failure():
    result = validate_response("  ")

    assert result.quality_score == 0.0
    assert result.grounding_score == 0.0
    assert result.completeness_score == 0.0
    assert result.hallucinations


def test_missing_source_discloses_grounding_not_checked():
    result = validate_response('{"message":"Hello"}')

    assert result.grounding_score == 0.0
    assert result.grounding_available is False
    assert any(
        "no source content" in warning.lower()
        for warning in result.validation_warnings
    )
    assert not any(
        "no source content" in issue.lower()
        for issue in result.hallucinations
    )


def test_paraphrased_numeric_claim_is_supported():
    source = "The product includes a 14-day trial period."
    response = "The trial period is 14 days long."

    result = validate_response(
        response_text=response,
        source_content=source,
    )

    assert result.grounding_available is True
    assert result.contradictions == []
    assert any(
        finding.classification == "supported"
        for finding in result.evidence_findings
    )


def test_numeric_contradiction_is_detected():
    source = "The product includes a 14-day trial period."
    response = "The trial period is 30 days."

    result = validate_response(
        response_text=response,
        source_content=source,
    )

    assert result.grounding_available is True
    assert result.contradictions
    assert any(
        finding.classification == "contradicted"
        for finding in result.evidence_findings
    )


def test_text_claim_is_supported_by_source():
    text = "Python is used for backend development."

    result = validate_response(
        response_text=text,
        source_content=text,
    )

    assert result.grounding_available is True
    assert result.contradictions == []
    assert any(
        finding.classification == "supported"
        for finding in result.evidence_findings
    )


def test_date_claim_supported_by_source():
    findings = extract_evidence_findings(
        '{"launch_date": "15 October 2026"}',
        "The product launch date is 15 October 2026.",
    )

    assert len(findings) == 1
    assert findings[0].classification == "supported"


def test_conflicting_date_is_detected():
    findings = extract_evidence_findings(
        '{"launch_date": "20 October 2026"}',
        "The product launch date is 15 October 2026.",
    )

    assert len(findings) == 1
    assert findings[0].classification == "contradicted"


def test_currency_claim_supported_by_source():
    findings = extract_evidence_findings(
        '{"monthly_price": "$20"}',
        "The monthly subscription price is $20.",
    )

    assert len(findings) == 1
    assert findings[0].classification == "supported"


def test_conflicting_currency_amount_is_detected():
    findings = extract_evidence_findings(
        '{"monthly_price": "$30"}',
        "The monthly subscription price is $20.",
    )

    assert len(findings) == 1
    assert findings[0].classification == "contradicted"


def test_mixed_text_and_numbers_are_supported():
    source = (
        "The trial lasts 14 days. "
        "The monthly subscription costs $20."
    )

    result = validate_response(
        response_text=source,
        source_content=source,
    )

    assert result.grounding_available is True
    assert result.contradictions == []
    assert len(result.evidence_findings) == 2
    assert all(
        finding.classification == "supported"
        for finding in result.evidence_findings
    )


def test_missing_evidence_is_not_treated_as_proof_of_falsehood():
    findings = extract_evidence_findings(
        '{"approval_code": "APPROVAL-XYZ-789"}',
        "The company is based in Chennai.",
    )

    assert len(findings) == 1
    assert findings[0].classification == "unsupported"
    assert "does not necessarily mean false" in (
        findings[0].explanation.lower()
    )

def test_no_source_means_grounding_is_unavailable():
    result = validate_response(
        response_text="Python supports backend development.",
        source_content=None,
    )

    assert result.grounding_available is False
    assert result.grounding_score == 0.0
    assert any(
        "grounding could not be verified" in warning.lower()
        for warning in result.validation_warnings
    )


def test_numeric_substring_does_not_count_as_evidence():
    assert not _value_is_supported("25", "The recorded value is 125.")
    assert _value_is_supported("25", "The recorded value is 25.")


def test_numeric_grounding_handles_decimals_and_percentages():
    assert _value_is_supported("3.5", "The measured value is 3.5.")
    assert _value_is_supported("20%", "The success rate is 20%.")

    assert not _value_is_supported("3.5", "The measured value is 13.5.")
    assert not _value_is_supported("20%", "The success rate is 120%.")


def test_different_numbers_for_unrelated_facts_are_not_contradictions():
    assert not detect_numeric_contradiction(
        "launch_year: 2027",
        "The company has 42 employees.",
        "The company has 42 employees.",
    )


def test_schema_rejects_wrong_json_value_type():
    schema = {
        "type": "object",
        "properties": {"age": {"type": "integer"}},
        "required": ["age"],
    }

    result = validate_response(
        '{"age": "twenty"}',
        "The person's age is twenty.",
        schema,
    )

    assert result.completeness_score == 50.0
    assert result.quality_score <= 25.0
    assert any(
        "JSON/schema validation failed" in issue
        for issue in result.hallucinations
    )



def test_refund_period_supports_30_days_without_false_contradiction():
    source = (
        "Customers can request a refund within 30 days of purchase. "
        "Refund requests submitted after 30 days are not eligible."
    )
    response = (
        "According to the source, customers have 30 days to request a refund."
    )

    result = validate_response(
        response_text=response,
        source_content=source,
    )

    assert not result.contradictions
    assert any(
        finding.classification == "supported"
        for finding in result.evidence_findings
    )
