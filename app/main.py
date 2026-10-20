
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import initialize_database
from app.routers import execution, failures
from app.routers import benchmark

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize application resources when FastAPI starts."""
    initialize_database()
    yield


app = FastAPI(
    title="AI Response Quality Gate",
    description=(
        "Validate AI responses, classify failures, "
        "and recover from errors."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(execution.router)
app.include_router(failures.router)
app.include_router(benchmark.router)


@app.get("/")
def home():
    return {
        "message": "AI Response Quality Gate API is running",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}
