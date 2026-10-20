# AI Response Quality Gate — Frontend

This is the React frontend for the AI Response Quality Gate application. It communicates with the FastAPI backend to submit requests, display AI response evaluation results, and review execution history and benchmarking information.

## Technology Stack

- React
- Vite
- JavaScript
- npm

## Prerequisites

- Node.js and npm
- The AI Response Quality Gate backend running locally
- Ollama running with the required model available for backend requests

## Installation

From the `frontend` directory, install dependencies:

```bash
npm install
```

## Run the Development Server

```bash
npm run dev
```

Open the local URL printed by Vite, usually:

http://localhost:5173

## Backend Connection

The frontend requires the FastAPI backend to be running. Start the backend from the project root:

```bash
uvicorn app.main:app --reload
```

The default backend address is:

http://127.0.0.1:8000

The interactive API documentation is available at:

http://127.0.0.1:8000/docs

## Production Build

Create a production build:

```bash
npm run build
```

Preview the production build locally:

```bash
npm run preview
```

## Related Documentation

See the root `README.md` for the complete project overview, backend setup, API endpoints, testing instructions, and configuration details.