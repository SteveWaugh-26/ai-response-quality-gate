# AI Response Quality Gate — Approach and Architecture

## 1. Project Overview

AI Response Quality Gate is a proof-of-concept application that evaluates AI-generated responses for quality, grounding, and completeness. It uses locally hosted language models through Ollama and provides a FastAPI backend and React frontend.

The application aims to identify questionable responses, apply recovery strategies where configured, and preserve execution information for debugging and comparison.

## 2. Technology Stack

- Backend: Python and FastAPI
- Data validation: Pydantic and JSON Schema
- Language model runtime: Ollama
- Models used: Llama 3.2 3B and Qwen3 4B
- Database: SQLite
- Frontend: React, Vite, and JavaScript
- Testing: pytest
- HTTP client: HTTPX

## 3. Architecture

The application is organized into the following layers.

### API layer

The FastAPI application exposes routers for execution, failures, and benchmarking.

- `app/main.py`: application entry point and API setup
- `app/routers/execution.py`: execution-related endpoints
- `app/routers/failures.py`: failure-related endpoint
- `app/routers/benchmark.py`: benchmark-related endpoints

### Service layer

- `app/services/llm_service.py`: communicates with the local language model runtime
- `app/services/validation_service.py`: evaluates model responses
- `app/services/recovery_service.py`: contains response recovery logic
- `app/services/document_service.py`: supports document-based processing

### Data layer

- `app/db/database.py`: database operations
- `app/db/executions.db`: local SQLite database used during development; this file should not be committed to the public repository

### Models and configuration

- `app/models.py`: request and response data models
- `app/config.py`: model endpoint, default model, timeout, database path, and retry limit

## 4. Execution and Validation Workflow

The intended workflow is:

1. A user submits a prompt, with optional source content or an expected JSON schema.
2. The API passes the request to the model execution service.
3. The generated response is passed to the validation service.
4. Validation results and applicable quality metrics are collected.
5. If validation identifies a failure, configured recovery or retry logic may be applied.
6. A fallback model may be used when the relevant conditions are met.
7. The final result and execution information are returned and may be saved to SQLite.
8. The frontend lets users inspect execution results and available history.

Exact validation rules, score calculations, and recovery decisions are defined by the implementation in the service modules.

## 5. Recovery and Reliability

The project includes recovery logic intended to support retry handling, response repair, and fallback model execution.

The configured defaults in `app/config.py` are:

- Ollama URL: `http://localhost:11434`
- Primary model: `llama3.2:3b`
- Request timeout: 120 seconds
- Maximum retries: 2
- Database path: `app/db/executions.db`

A fallback model is configured or selected through the applicable execution logic. Actual fallback behavior depends on the implementation and request settings.

## 6. API Overview

The application includes the following documented API routes:

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/execute` | Execute a request and evaluate its response |
| GET | `/api/execution/{execution_id}` | Retrieve a saved execution |
| GET | `/api/executions` | Retrieve execution history |
| POST | `/api/execute-document` | Process a document-based request |
| GET | `/api/execution/{execution_id}/report` | Retrieve an execution report |
| GET | `/api/failures` | Retrieve recorded failures |
| POST | `/api/benchmark` | Run a model benchmark |
| GET | `/api/benchmarks` | Retrieve benchmark runs |
| GET | `/api/benchmark/{run_id}` | Retrieve a benchmark run |

Run the backend and visit `/docs` for the live API schema and request formats.

## 7. Persistence and Observability

SQLite provides local persistence for execution-related data. The API also supports execution history, failure inspection, reports, and benchmarking routes.

Execution records can help with debugging and comparing behavior across runs. Latency and other metrics should be interpreted in the context of the machine, model, prompt, and current runtime conditions.

## 8. Testing and Verification

Backend tests are run with:

```bash
pytest -q
```

The frontend production build is checked with:

```bash
cd frontend
npm run build
```

At the time of writing, the project test run completed with 55 passing tests, and the Vite production build succeeded. Re-run both commands before the final submission.

## 9. Limitations

- Small local models may produce inaccurate or incomplete answers.
- Quality and grounding scores are indicators, not guarantees of factual correctness.
- Validation depends on the available source content, schema, and configured rules.
- Latency and output quality vary by hardware, model, and prompt.
- Benchmark results are environment-dependent and should be collected under comparable conditions.

## 10. Security and Repository Hygiene

- Do not commit credentials, private documents, or sensitive data.
- Keep `.venv`, `frontend/node_modules`, frontend build output, and the local SQLite database out of Git.
- Review generated reports and screenshots before publishing.
- Do not describe measured performance unless it was actually observed and recorded.

