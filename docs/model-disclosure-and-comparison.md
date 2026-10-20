# AI Response Quality Gate — Model Disclosure and Comparison

## 1. Model Disclosure

This proof of concept uses locally hosted language models through Ollama. The application is designed to evaluate generated responses and inspect differences in quality, grounding, completeness, structured-output reliability, and latency.

### Model A: Llama 3.2 3B

- **Model name:** `llama3.2:3b`
- **Model type:** Small language model (SLM) for this project's model-size classification.
- **Use case:** Primary model for response generation and quality-gate evaluation.
- **Platform:** Ollama.
- **Deployment type:** Local inference through the Ollama HTTP API.
- **Reason for selection:** Suitable for testing a lightweight local inference workflow without requiring a hosted model API.
- **Limitation observed:** In one development test, this model returned a 90-day refund period when the provided source stated 30 days. This illustrates why generated responses need source-grounded validation.

### Model B: Qwen3 4B

- **Model name:** `qwen3:4b`
- **Model type:** Small language model (SLM) for this project's model-size classification.
- **Use case:** Alternative model for comparative evaluation and fallback testing.
- **Platform:** Ollama.
- **Deployment type:** Local inference through the Ollama HTTP API.
- **Reason for selection:** Provides a second locally runnable model for comparison without requiring a separate hosted inference service.
- **Limitation observed:** Model outputs may still require validation. The development test described below is only one example and does not establish general performance across prompts.

## 2. Comparison Methodology

The benchmark endpoint runs the same test cases against two distinct model names. Each case can include a prompt, optional source content, and an optional expected JSON Schema.

The benchmark records the following measurements for each model:

| Metric | Meaning |
|---|---|
| Average quality score | Mean quality score returned by the validation service |
| Average grounding score | Mean grounding score returned by the validation service |
| Average completeness score | Mean completeness score returned by the validation service |
| Average latency (ms) | Mean measured execution time for the benchmark cases |
| JSON reliability (%) | Percentage of measured JSON-required cases that return syntactically valid JSON |
| Schema reliability (%) | Percentage of measured boolean schema outcomes that pass |
| Validation pass rate (%) | Percentage of cases passing the application's heuristic quality gate |
| Contradictions | Contradictions identified by the validator |
| Evidence findings | Evidence-related findings returned by the validator |
| Recommended actions | Actions suggested by the validation service |

JSON syntax validity, JSON Schema conformance, and quality-gate outcomes are tracked separately. A missing source makes grounding unavailable; it does not automatically fail the quality gate. The benchmark's validation pass rate is heuristic and does not prove factual correctness.

## 3. Benchmark Results

The following measurements were recorded from one benchmark run on the development machine.

- **Benchmark run ID:** `bfa4af1b-b21d-4cab-bef2-92dfa0876394`
- **Test cases:** 1 source-grounded JSON response case
- **Primary model:** `llama3.2:3b`
- **Comparison model:** `qwen3:4b`

| Metric | Llama 3.2 3B | Qwen3 4B |
|---|---:|---:|
| Cases run | 1 | 1 |
| Successful runs | 1 | 1 |
| Average quality score | 100.0 | 100.0 |
| Average grounding score | 100.0 | 100.0 |
| Average completeness score | 100.0 | 100.0 |
| Average latency (ms) | 2859.21 | 12453.82 |
| JSON reliability (%) | 100.0 | 100.0 |
| Schema reliability (%) | 100.0 | 100.0 |
| Validation pass rate (%) | 100.0 | 100.0 |

Both models returned `{"refund_days": 30}`, matching the supplied source content and expected JSON Schema. In this run, Llama 3.2 3B was approximately 4.35 times faster than Qwen3 4B.

These measurements represent one test case on one machine. They do not establish general performance across other prompts, datasets, or hardware. The validation pass rate is heuristic and does not prove factual correctness.

## 4. Observed Development Test

During one development test, the source content specified a 30-day refund period.

- The primary model, `llama3.2:3b`, returned an incorrect 90-day period.
- The fallback model, `qwen3:4b`, returned the source-supported 30-day period.
- The fallback response passed the configured validation checks in that test.

This is a single observed test case, not a controlled benchmark. It should not be used to claim that one model is generally more accurate or faster than the other.

## 5. Qualitative Comparison and Limitations

Both models run locally through Ollama, making them useful for a local proof of concept. The benchmark is intended to measure differences rather than assume that a model is superior based only on its name or size.

The following conclusions should be made only after collecting results:

- **Response quality:** Compare average quality scores and inspect representative responses.
- **Grounding:** Compare grounding scores and evidence findings when source content is supplied.
- **Completeness:** Compare completeness scores against the same cases.
- **Structured output:** Compare JSON and schema reliability on cases that require structured output.
- **Latency:** Compare average latency under the same machine and test conditions.
- **Limitations:** Inspect incorrect claims, contradictions, execution errors, and failed validation cases.

## 6. Recommended Use Cases

Recommendations should be finalized after reviewing the measured results.

- **Llama 3.2 3B:** Candidate primary model for a lightweight local workflow, subject to measured quality and reliability.
- **Qwen3 4B:** Candidate comparison or fallback model, subject to measured quality, reliability, and latency.

These are initial testing roles, not claims of production superiority.

## 7. Production Recommendation

Do not select a production model based only on a single successful example or a single average score. Use a representative evaluation dataset, source-grounded factual checks, structured-output tests, repeatable latency measurements, and application-specific acceptance thresholds.

For this proof of concept, the quality gate provides useful debugging signals and recovery behavior. It does not guarantee that every accepted response is correct.

## 8. Cost vs. Performance

Both models are run locally in this setup, so the application does not require a hosted model API for inference. Local inference still uses machine resources such as memory, CPU, and potentially GPU.

No verified monetary cost or energy measurements are recorded in this document. A fair cost-performance comparison would require measured resource usage, hardware details, and any applicable hosting or operating costs.

