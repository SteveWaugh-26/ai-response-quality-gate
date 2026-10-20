
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict


class ExecuteRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    expected_schema: Optional[Dict[str, Any]] = None
    source_content: Optional[str] = None
    model: Optional[str] = None
    fallback_model: Optional[str] = None
    max_retries: int = Field(default=2, ge=0, le=5)


class EvidenceFinding(BaseModel):
    claim: str
    classification: Literal[
        "supported",
        "contradicted",
        "unsupported",
        "abstained",
    ]
    evidence: str = ""
    explanation: str


class ValidationResult(BaseModel):
    quality_score: float
    grounding_score: float
    completeness_score: float
    contradictions: List[str] = Field(default_factory=list)
    hallucinations: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    evidence_findings: List[EvidenceFinding] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)
    grounding_available: bool = True


class ExecuteResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    execution_id: str
    status: str

    # Model disclosure.
    model_used: Optional[str] = None
    fallback_model: Optional[str] = None

    original_response: Optional[str] = None
    final_response: Optional[str] = None

    # Validation before and after recovery.
    initial_validation: Optional[ValidationResult] = None
    validation: Optional[ValidationResult] = None

    failure_type: Optional[str] = None
    recovery_strategy: Optional[str] = None
    retry_count: int = 0
    fallback_model_used: bool = False
    execution_trace: List[str] = Field(default_factory=list)
    total_latency_ms: float = 0.0
