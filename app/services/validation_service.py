
import json
import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Set, Tuple

from jsonschema import SchemaError, ValidationError, validate

from app.models import EvidenceFinding, ValidationResult


NEGATION_WORDS = {
    "not", "no", "never", "neither", "without", "cannot",
    "can't", "doesn't", "isn't", "aren't", "wasn't", "weren't",
    "didn't", "hasn't", "haven't", "won't", "don't", "shouldn't",
    "wouldn't", "couldn't", "mustn't",
}

STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "do", "does", "did", "has", "have", "had", "of",
    "to", "in", "on", "for", "with", "and", "or", "but", "by",
    "from", "at", "as", "it", "this", "that", "these", "those",
    "their", "they", "them", "he", "she", "we", "you", "i",
    "will", "can", "could", "would", "should", "may", "might",
}

GENERIC_KEYS = {
    "answer", "result", "response", "output", "value",
    "data", "message", "text",
}

ABSTENTION_VALUES = {
    "unknown", "not known", "not provided", "not available",
    "unavailable", "not specified", "unspecified", "not mentioned",
    "not stated", "not found", "not in source", "n/a", "na",
}

# Supports integers, comma-grouped numbers, decimals, signs and percentages.
_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])[+-]?"
    r"(?:\d{1,3}(?:,\d{3})+|\d+)"
    r"(?:\.\d+)?%?"
    r"(?!\w)"
)

# Split on sentence-ending punctuation or line boundaries.
_SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+|\n+")


def normalize_words(text: str) -> Set[str]:
    """Return lowercase words and numeric tokens from text."""
    if not isinstance(text, str):
        return set()

    words = re.findall(
        r"[a-z]+(?:'[a-z]+)?|[+-]?"
        r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?",
        text.casefold(),
    )
    return {word.replace(",", "") for word in words}


def _canonical_number(number: str) -> str:
    """Normalize numeric formatting without dropping percentage units."""
    number = number.replace(",", "").strip()
    is_percentage = number.endswith("%")
    if is_percentage:
        number = number[:-1]

    try:
        value = Decimal(number)
    except InvalidOperation:
        return number + ("%" if is_percentage else "")

    if not value.is_finite():
        return number + ("%" if is_percentage else "")

    normalized = format(value.normalize(), "f")
    if normalized == "-0":
        normalized = "0"

    return normalized + ("%" if is_percentage else "")


def extract_numbers(text: str) -> Set[str]:
    """Extract normalized integer, decimal, signed and percentage values."""
    if not isinstance(text, str):
        return set()

    return {
        _canonical_number(match)
        for match in _NUMBER_PATTERN.findall(text)
    }


def _is_negated(text: str) -> bool:
    """Detect common negation words; this is a heuristic, not NLP parsing."""
    words = normalize_words(text)
    return bool(words & NEGATION_WORDS) or any(
        word.endswith("n't") for word in words
    )


def _normalize_word(word: str) -> str:
    """Conservatively normalize common English word forms."""
    word = word.casefold()

    if word == "uses":
        return "use"

    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"

    if word.endswith("ing") and len(word) > 5:
        base = word[:-3]
        if len(base) > 2 and base[-1] == base[-2]:
            base = base[:-1]
        return base

    if word.endswith("ed") and len(word) > 4:
        return word[:-2]

    if word.endswith("s") and len(word) > 3:
        return word[:-1]

    return word


def _content_words(text: str) -> Set[str]:
    """Return normalized content words, excluding filler words and numbers."""
    result: Set[str] = set()

    for word in normalize_words(text):
        if word in STOP_WORDS or word in NEGATION_WORDS:
            continue
        if extract_numbers(word):
            continue
        result.add(_normalize_word(word))

    return result


def _meaningful_key(key: Any) -> str:
    """Clean a JSON field name and discard generic labels."""
    if not isinstance(key, str):
        return ""

    cleaned = key.replace("_", " ").replace("-", " ").strip()
    if cleaned.casefold() in GENERIC_KEYS:
        return ""

    return cleaned


def _split_sentences(text: str) -> List[str]:
    """Split text into non-empty sentence-like units."""
    if not isinstance(text, str):
        return []

    return [
        part.strip()
        for part in _SENTENCE_PATTERN.split(text)
        if part.strip()
    ]


def parse_response_claims(response_text: str) -> List[str]:
    """
    Extract plain-text sentences or leaf values from JSON.

    JSON field names are retained as context, so a value such as
    {"employee_count": 25} becomes "employee count: 25".
    """
    if not isinstance(response_text, str) or not response_text.strip():
        return []

    try:
        parsed = json.loads(response_text)
    except (json.JSONDecodeError, TypeError):
        return _split_sentences(response_text)

    claims: List[str] = []

    def collect(value: Any, context: str = "") -> None:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                key_context = _meaningful_key(key)
                combined = " ".join(
                    part for part in (context, key_context) if part
                )
                collect(nested_value, combined)

        elif isinstance(value, list):
            for item in value:
                collect(item, context)

        elif isinstance(value, str):
            claims.append(f"{context}: {value}" if context else value)

        elif value is None:
            claims.append(f"{context}: null" if context else "null")

        elif isinstance(value, bool):
            text_value = "true" if value else "false"
            claims.append(
                f"{context}: {text_value}" if context else text_value
            )

        elif isinstance(value, (int, float)):
            # JSON does not permit NaN or Infinity, but Python's json parser
            # may accept them. Avoid passing non-finite values as claims.
            if isinstance(value, float) and not math.isfinite(value):
                text_value = str(value)
            else:
                text_value = str(value)
            claims.append(
                f"{context}: {text_value}" if context else text_value
            )

    collect(parsed)
    return claims


def extract_response_facts(response_text: str) -> str:
    """Return extracted claims as a single text string."""
    return " ".join(parse_response_claims(response_text))


def _split_claim(claim: str) -> Tuple[str, str]:
    """Separate a field label from its value when the claim is field-based."""
    if not isinstance(claim, str) or ":" not in claim:
        return "", claim.strip() if isinstance(claim, str) else ""

    key, value = claim.split(":", 1)
    return key.strip(), value.strip()


def _word_overlap(claim: str, sentence: str) -> float:
    """Measure the fraction of claim keywords present in a source sentence."""
    claim_words = _content_words(claim)
    source_words = _content_words(sentence)

    if not claim_words:
        return 0.0

    return len(claim_words & source_words) / len(claim_words)


def _is_abstention_value(value: str) -> bool:
    """Identify explicit statements that a value is unknown or unavailable."""
    if not isinstance(value, str):
        return False

    normalized = re.sub(r"[^a-z0-9/ ]+", "", value.casefold())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized in ABSTENTION_VALUES


def _value_is_supported(value: str, sentence: str) -> bool:
    """
    Check whether a value has direct lexical evidence in one source sentence.

    This deliberately conservative check is not a semantic fact verifier.
    Numeric values must match before a phrase match is accepted.
    """
    if not isinstance(value, str) or not isinstance(sentence, str):
        return False

    value = value.strip().strip("\"'")
    sentence = sentence.strip()

    if not value or not sentence:
        return False

    value_numbers = extract_numbers(value)
    source_numbers = extract_numbers(sentence)

    # Never let a number match merely because its digits are a substring
    # of a different number. Percentages remain distinct from plain numbers.
    if value_numbers and not value_numbers.issubset(source_numbers):
        return False

    # A case-insensitive phrase match is useful for names and exact values.
    if value.casefold() in sentence.casefold():
        return True

    value_words = _content_words(value)
    source_words = _content_words(sentence)

    if not value_words:
        return bool(value_numbers and value_numbers.issubset(source_numbers))

    # For short names/labels, require every content word.
    if len(value_words) <= 3 and value_words.issubset(source_words):
        return True

    # Allow strong lexical paraphrases, but do not call these semantic proof.
    if _word_overlap(value, sentence) >= 0.8:
        return True

    # Numeric paraphrases need both matching numbers and enough context.
    shared_words = value_words & source_words
    return (
        bool(value_numbers)
        and value_numbers.issubset(source_numbers)
        and len(shared_words) >= 2
        and len(shared_words) / len(value_words) >= 0.5
    )


def detect_numeric_contradiction(
    claim: str,
    sentence: str,
    source_content: Optional[str] = None,
) -> bool:
    """
    Flag a likely numeric conflict only when the claim and source share context.

    Different numbers alone do not prove a contradiction. Units, dates,
    ranges, and whether both values describe the same fact still matter.
    """
    if not isinstance(claim, str) or not isinstance(sentence, str):
        return False

    key, value = _split_claim(claim)
    claim_numbers = extract_numbers(value)
    source_numbers = extract_numbers(sentence)

    if not claim_numbers or not source_numbers:
        return False

    if claim_numbers.issubset(source_numbers):
        return False

    context_words = _content_words(key or claim)
    source_words = _content_words(sentence)

    # Field labels provide the strongest available context for JSON claims.
    if context_words:
        shared = context_words & source_words
        if shared:
            return True
        return False

    # For prose claims, require some subject/context overlap and a clear
    # numeric mismatch in the relevant sentence.
    claim_words = _content_words(value)
    shared = claim_words & source_words

    if shared and len(claim_words) > 0:
        overlap = len(shared) / len(claim_words)
        if overlap >= 0.5:
            return True

    # With no meaningful context, do not infer a contradiction merely
    # because a source contains a different number.
    all_source_numbers = extract_numbers(source_content or sentence)
    return (
        not context_words
        and not claim_words
        and len(claim_numbers) == 1
        and len(source_numbers) == 1
        and len(all_source_numbers) == 1
    )



def _detect_text_contradiction(claim: str, sentence: str) -> bool:
    """
    Conservatively detect possible negation conflicts.

    Avoid flagging explanatory statements that merely discuss or reject
    a claim as contradictions. Lexical overlap alone is not sufficient.
    """
    if not isinstance(claim, str) or not isinstance(sentence, str):
        return False

    key, value = _split_claim(claim)
    claim_text = f"{key} {value}".strip() if key else claim

    claim_words = _content_words(claim_text)
    source_words = _content_words(sentence)

    if not claim_words or not source_words:
        return False

    # Require meaningful subject overlap before comparing negation.
    overlap = len(claim_words & source_words) / len(claim_words)
    if overlap < 0.5:
        return False

    # A negation mismatch is only a heuristic, not proof of contradiction.
    return _is_negated(claim_text) != _is_negated(sentence)



def extract_evidence_findings(
    response_text: str,
    source_content: Optional[str],
) -> List[EvidenceFinding]:
    """Classify extracted claims as supported, unsupported, contradicted or abstained."""
    if not isinstance(source_content, str) or not source_content.strip():
        return []

    claims = parse_response_claims(response_text)
    source_sentences = _split_sentences(source_content)
    findings: List[EvidenceFinding] = []

    for claim in claims:
        if not normalize_words(claim):
            continue

        _, value = _split_claim(claim)

        if _is_abstention_value(value):
            findings.append(
                EvidenceFinding(
                    claim=claim,
                    classification="abstained",
                    evidence="",
                    explanation=(
                        "The response explicitly indicates that the value is "
                        "unknown or absent from the source. It is treated as "
                        "an abstention, not as a factual assertion."
                    ),
                )
            )
            continue

        supported_sentence = next(
            (
                sentence
                for sentence in source_sentences
                if _value_is_supported(value, sentence)
            ),
            "",
        )

        best_sentence = ""
        best_overlap = 0.0
        contradiction_sentence = ""
        contradiction_reason = ""

        for sentence in source_sentences:
            overlap = max(
                _word_overlap(claim, sentence),
                _word_overlap(value, sentence),
            )

            if overlap > best_overlap:
                best_overlap = overlap
                best_sentence = sentence

            # A directly supported value should not be downgraded because
            # a separate heuristic finds a possible conflict.
            if supported_sentence:
                continue

            if detect_numeric_contradiction(claim, sentence, source_content):
                contradiction_sentence = sentence
                contradiction_reason = "numeric"
                break

            if _detect_text_contradiction(claim, sentence):
                contradiction_sentence = sentence
                contradiction_reason = "negation"
                break

        if contradiction_sentence:
            classification = "contradicted"
            evidence = contradiction_sentence

            if contradiction_reason == "numeric":
                explanation = (
                    "The numeric value differs from a source statement with "
                    "overlapping subject wording. Check that both values "
                    "refer to the same fact, time period, and unit."
                )
            else:
                explanation = (
                    "The claim and source may differ in negation. "
                    "Verify the intended meaning before treating this "
                    "as a confirmed contradiction."
                )

        elif supported_sentence:
            classification = "supported"
            evidence = supported_sentence
            explanation = (
                "The response value has a direct lexical match in the source. "
                "This check does not establish broader factual accuracy."
            )

        elif best_overlap >= 0.5:
            classification = "unsupported"
            evidence = best_sentence
            explanation = (
                "Some wording overlaps with the source, but the claim value "
                "could not be sufficiently verified. Unsupported does not "
                "necessarily mean false."
            )

        else:
            classification = "unsupported"
            evidence = ""
            explanation = (
                "No sufficiently strong evidence match was found. "
                "Unsupported does not necessarily mean false."
            )

        findings.append(
            EvidenceFinding(
                claim=claim,
                classification=classification,
                evidence=evidence,
                explanation=explanation,
            )
        )

    return findings


def _arithmetic_findings(source_content: str) -> List[str]:
    """
    Report simple multiplication patterns as diagnostic notes.

    These notes are not proof that the source or response is correct.
    """
    if not isinstance(source_content, str):
        return []

    findings: List[str] = []
    pattern = re.compile(
        r"(\d+(?:\.\d+)?)\s+(\w+),?\s+with\s+"
        r"(\d+(?:\.\d+)?)\s+(\w+)\s+in\s+each\s+\2",
        re.IGNORECASE,
    )

    for match in pattern.finditer(source_content):
        group_count = Decimal(match.group(1))
        item_count = Decimal(match.group(3))
        item_name = match.group(4)
        expected_total = group_count * item_count

        findings.append(
            f"Source arithmetic check: {group_count:g} groups × "
            f"{item_count:g} {item_name} per group = {expected_total:g}."
        )

    return findings


def validate_response(
    response_text: str,
    source_content: Optional[str] = None,
    expected_schema: Optional[Dict[str, Any]] = None,
) -> ValidationResult:
    """
    Evaluate response structure and compare claims with supplied source text.

    quality_score is a heuristic score, not a probability of truth.
    completeness_score measures schema/structure status only when no separate
    semantic completeness specification is available.
    """
    issues: List[str] = []
    actions: List[str] = []
    contradictions: List[str] = []
    warnings: List[str] = []

    has_source = (
        isinstance(source_content, str) and bool(source_content.strip())
    )

    if not isinstance(response_text, str) or not response_text.strip():
        return ValidationResult(
            quality_score=0.0,
            grounding_score=0.0,
            completeness_score=0.0,
            contradictions=[],
            hallucinations=["The response is empty or is not valid text."],
            recommended_actions=["Retry generation with a clearer prompt."],
            evidence_findings=[],
            validation_warnings=[],
            grounding_available=has_source,
        )

    schema_failed = False
    invalid_schema = False

    if expected_schema is not None:
        try:
            parsed_response = json.loads(response_text)
        except (json.JSONDecodeError, TypeError) as exc:
            schema_failed = True
            if isinstance(exc, json.JSONDecodeError):
                detail = (
                    f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
                )
            else:
                detail = str(exc)

            issues.append(f"JSON parsing failed: {detail}")
            actions.append(
                "Repair the response to produce valid JSON matching the schema."
            )
        else:
            try:
                validate(instance=parsed_response, schema=expected_schema)
            except ValidationError as exc:
                schema_failed = True
                issues.append(
                    f"JSON/schema validation failed: {exc.message}"
                )
                actions.append(
                    "Repair the response to match the expected JSON schema."
                )
            except SchemaError as exc:
                invalid_schema = True
                issues.append(
                    f"The expected JSON schema is invalid: {exc.message}"
                )
                actions.append(
                    "Correct the expected JSON schema and try again."
                )
            except (TypeError, ValueError) as exc:
                invalid_schema = True
                issues.append(
                    f"The expected JSON schema has an invalid structure: {exc}"
                )
                actions.append(
                    "Correct the expected JSON schema and try again."
                )

    evidence_findings = extract_evidence_findings(
        response_text,
        source_content,
    )

    for finding in evidence_findings:
        if finding.classification == "contradicted":
            contradictions.append(finding.claim)

    if contradictions:
        issues.append(
            "Contradicted claims detected: " + "; ".join(contradictions)
        )
        actions.append(
            "Review the conflicting evidence and correct or remove claims "
            "that genuinely contradict the source."
        )

    unsupported_findings = [
        finding
        for finding in evidence_findings
        if finding.classification == "unsupported"
    ]

    if unsupported_findings:
        for finding in unsupported_findings:
            issue = (
                "Unsupported claim (not verified by source): "
                f"{finding.claim}"
            )
            if issue not in issues:
                issues.append(issue)

        actions.append(
            "Verify unsupported claims or explicitly state when a value "
            "is unknown or absent from the source."
        )

    if has_source:
        claims = parse_response_claims(response_text)
        claim_words: Set[str] = set()
        factual_claim_count = 0

        for claim in claims:
            _, value = _split_claim(claim)

            if _is_abstention_value(value):
                continue

            factual_claim_count += 1
            claim_words.update(normalize_words(value))

        source_words = normalize_words(source_content)

        lexical_score = (
            len(claim_words & source_words) / len(claim_words) * 100
            if claim_words
            else (100.0 if factual_claim_count == 0 else 0.0)
        )

        assessed_findings = [
            finding
            for finding in evidence_findings
            if finding.classification != "abstained"
        ]

        if assessed_findings:
            supported_count = sum(
                finding.classification == "supported"
                for finding in assessed_findings
            )
            evidence_score = (
                supported_count / len(assessed_findings) * 100
            )
            grounding_score = (lexical_score + evidence_score) / 2
        elif evidence_findings and all(
            finding.classification == "abstained"
            for finding in evidence_findings
        ):
            grounding_score = 100.0
        else:
            grounding_score = lexical_score

        # Caps keep strong word overlap from hiding obvious evidence problems.
        if unsupported_findings:
            grounding_score = min(grounding_score, 70.0)

        if contradictions:
            grounding_score = min(grounding_score, 25.0)

        grounding_score = round(grounding_score, 2)

        if grounding_score < 50:
            if not contradictions:
                issues.append(
                    "The response has low evidence overlap with the source."
                )
            actions.append(
                "Review the response and retain only claims that can be "
                "supported by the supplied source."
            )

        warnings.extend(_arithmetic_findings(source_content))

    else:
        grounding_score = 0.0
        warnings.append(
            "Grounding could not be verified because no source content "
            "was provided. A zero grounding score here means unavailable, "
            "not that the response has been proven false."
        )
        actions.append(
            "Provide source content to enable evidence-based validation."
        )

    if invalid_schema:
        completeness_score = 0.0
        grounding_score = min(grounding_score, 50.0)
    elif schema_failed:
        completeness_score = 50.0
    else:
        # Without an expected schema or task-specific checklist, semantic
        # completeness cannot be reliably determined.
        completeness_score = 100.0
        if expected_schema is None:
            warnings.append(
                "No expected schema was supplied; completeness reflects "
                "structural validation status, not semantic completeness."
            )

    quality_score = round(
        (grounding_score + completeness_score) / 2,
        2,
    )

    # Structural failures must limit the overall quality score.
    if invalid_schema:
        quality_score = 0.0
    elif schema_failed:
        quality_score = min(quality_score, 25.0)

    return ValidationResult(
        quality_score=round(quality_score, 2),
        grounding_score=round(grounding_score, 2),
        completeness_score=round(completeness_score, 2),
        contradictions=list(dict.fromkeys(contradictions)),
        # Kept for compatibility with the existing model/API. This list
        # contains validation issues; not every issue is a proven hallucination.
        hallucinations=list(dict.fromkeys(issues)),
        recommended_actions=list(dict.fromkeys(actions)),
        evidence_findings=evidence_findings,
        validation_warnings=list(dict.fromkeys(warnings)),
        grounding_available=has_source,
    )
