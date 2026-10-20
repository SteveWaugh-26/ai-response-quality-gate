# AI Response Quality Gate

A full-stack application that evaluates AI-generated responses for quality, grounding, and completeness. It includes response validation, recovery and retries, fallback models, execution history, document processing, reports, and benchmarking.

## Features

- Generate responses using locally hosted AI models.
- Evaluate response quality, grounding, and completeness.
- Validate outputs using configurable rules and JSON schemas.
- Retry or recover responses that fail validation.
- Switch to a fallback model when configured conditions are met.
- Store execution history using SQLite.
- Support document-based execution.
- Generate JSON execution reports.
- Run model benchmarks and review failures.

## Technology Stack

- **Backend:** Python, FastAPI, Pydantic, HTTPX, JSON Schema, SQLite
- **Frontend:** React, Vite, JavaScript
- **Local AI:** Ollama, Llama 3.2 3B, Qwen3 4B

## Project Structure

```text
ai-response-quality-gate/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── db/
│   ├── routers/
│   └── services/
├── frontend/
│   └── src/
├── tests/
├── docs/
├── requirements.txt
├── README.md
└── .gitignore
```

## Prerequisites

- Python 3.12
- Node.js and npm
- Ollama

## Installation and Setup

### 1. Download the AI models

Ensure Ollama is installed and running.

```bash
ollama pull llama3.2:3b
ollama pull qwen3:4b
ollama list
```

### 2. Install backend dependencies

Run from the project root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Start the backend

```bash
uvicorn app.main:app --reload
```

Backend URL: http://127.0.0.1:8000

Interactive API documentation: http://127.0.0.1:8000/docs

### 4. Start the frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, usually http://localhost:5173.

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/execute` | Execute a prompt and evaluate the response |
| GET | `/api/execution/{execution_id}` | Retrieve an execution |
| GET | `/api/executions` | Retrieve execution history |
| POST | `/api/execute-document` | Execute a document-based request |
| GET | `/api/execution/{execution_id}/report` | Retrieve an execution report |
| GET | `/api/failures` | Retrieve recorded failures |
| POST | `/api/benchmark` | Run a benchmark |
| GET | `/api/benchmarks` | Retrieve benchmark runs |
| GET | `/api/benchmark/{run_id}` | Retrieve a benchmark run |

For request and response details, start the backend and visit `/docs`.

## How It Works

1. The user submits a prompt or supported document.
2. The backend sends the request to a local Ollama model.
3. The response is checked against configured validation rules.
4. Quality, grounding, and completeness scores are calculated.
5. Failed responses may trigger retries, recovery, or fallback-model execution.
6. Execution results and metadata are stored in SQLite.
7. The frontend displays results, history, reports, and benchmarks.

## Testing

Run backend tests from the project root:

```bash
pytest -q
```

Build the frontend:

```bash
cd frontend
npm run build
```

## Configuration

Review `app/config.py` to configure the Ollama URL, default model, request timeout, database path, and retry limit.

- **Default Ollama URL:** `http://localhost:11434`
- **Default database:** `app/db/executions.db`

## Limitations

- AI responses and evaluation scores are not guaranteed to be correct.
- Grounding depends on the available source information and validation rules.
- Local model performance depends on hardware and model size.
- Benchmark results can vary between prompts and runs.

## Security

- Do not commit credentials, API keys, or sensitive documents.
- Keep virtual environments, local databases, and generated build files out of Git.
- Review documents before submitting them for processing.

## License

No license has been specified yet.