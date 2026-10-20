import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    db_path = Path(DATABASE_PATH).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _add_missing_columns(connection: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    for name, definition in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def initialize_database() -> None:
    """Create tables and safely migrate older project databases in place."""
    with get_connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS executions (
                execution_id TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                model TEXT,
                status TEXT NOT NULL,
                original_response TEXT,
                final_response TEXT,
                validation_json TEXT,
                failure_type TEXT,
                recovery_strategy TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                fallback_model_used INTEGER NOT NULL DEFAULT 0,
                execution_trace_json TEXT,
                total_latency_ms REAL NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        _add_missing_columns(connection, "executions", {
            "source_content": "TEXT",
            "expected_schema_json": "TEXT",
            "fallback_model": "TEXT",
        })
        connection.execute("CREATE INDEX IF NOT EXISTS idx_executions_created_at ON executions(created_at DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_executions_status_created_at ON executions(status, created_at DESC)")

        connection.execute(
            """CREATE TABLE IF NOT EXISTS benchmark_runs (
                run_id TEXT PRIMARY KEY,
                results_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        _add_missing_columns(connection, "benchmark_runs", {
            "models_json": "TEXT",
            "summaries_json": "TEXT",
            "cases_count": "INTEGER NOT NULL DEFAULT 0",
        })
        connection.execute("CREATE INDEX IF NOT EXISTS idx_benchmark_runs_created_at ON benchmark_runs(created_at DESC)")


def save_execution(record: Dict[str, Any]) -> None:
    for field in ("execution_id", "prompt", "status"):
        if field not in record:
            raise ValueError(f"Missing required execution field: {field}")

    validation_data = {
        "initial_validation": record.get("initial_validation"),
        "validation": record.get("validation"),
    }
    with get_connection() as connection:
        connection.execute(
            """INSERT OR REPLACE INTO executions (
                execution_id, prompt, model, status, original_response, final_response,
                validation_json, failure_type, recovery_strategy, retry_count,
                fallback_model_used, execution_trace_json, total_latency_ms,
                source_content, expected_schema_json, fallback_model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["execution_id"], record["prompt"], record.get("model"), record["status"],
                record.get("original_response"), record.get("final_response"), json.dumps(validation_data),
                record.get("failure_type"), record.get("recovery_strategy"), record.get("retry_count", 0),
                int(bool(record.get("fallback_model_used", False))),
                json.dumps(record.get("execution_trace", [])), record.get("total_latency_ms", 0),
                record.get("source_content"),
                json.dumps(record.get("expected_schema")) if record.get("expected_schema") is not None else None,
                record.get("fallback_model"),
            ),
        )


def _restore_execution_record(row: sqlite3.Row) -> Dict[str, Any]:
    record = dict(row)
    try:
        validation_data = json.loads(record.pop("validation_json", None) or "{}")
    except (json.JSONDecodeError, TypeError):
        validation_data = {}
    if isinstance(validation_data, dict) and ("initial_validation" in validation_data or "validation" in validation_data):
        record["initial_validation"] = validation_data.get("initial_validation")
        record["validation"] = validation_data.get("validation")
    else:
        record["initial_validation"] = None
        record["validation"] = validation_data or None
    try:
        record["execution_trace"] = json.loads(record.pop("execution_trace_json", None) or "[]")
    except (json.JSONDecodeError, TypeError):
        record.pop("execution_trace_json", None)
        record["execution_trace"] = []
    try:
        raw_schema = record.get("expected_schema_json")
        record["expected_schema"] = json.loads(raw_schema) if raw_schema else None
    except (json.JSONDecodeError, TypeError):
        record["expected_schema"] = None
    record["fallback_model_used"] = bool(record.get("fallback_model_used", False))
    return record


def get_execution(execution_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM executions WHERE execution_id = ?", (execution_id,)).fetchone()
    return _restore_execution_record(row) if row is not None else None


def list_executions(limit: int = 100) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT execution_id, prompt, model, status, failure_type, recovery_strategy,
                      retry_count, fallback_model_used, total_latency_ms, created_at, validation_json
               FROM executions ORDER BY created_at DESC, rowid DESC LIMIT ?""", (limit,)
        ).fetchall()
    records = [_restore_execution_record(row) for row in rows]
    for record in records:
        record["fallback_model_used"] = bool(record.get("fallback_model_used", False))
    return records


def list_failures(limit: int = 100) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT execution_id, prompt, model, status, failure_type, recovery_strategy,
                      retry_count, fallback_model_used, total_latency_ms, created_at
               FROM executions WHERE status = 'needs_review'
               ORDER BY created_at DESC, rowid DESC LIMIT ?""", (limit,)
        ).fetchall()
    records = [dict(row) for row in rows]
    for record in records:
        record["fallback_model_used"] = bool(record.get("fallback_model_used", False))
    return records


def save_benchmark(run_id: str, models: List[str], cases_count: int, summaries: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> None:
    with get_connection() as connection:
        connection.execute(
            """INSERT OR REPLACE INTO benchmark_runs
               (run_id, models_json, cases_count, summaries_json, results_json)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, json.dumps(models), cases_count, json.dumps(summaries), json.dumps(results)),
        )


def _restore_benchmark(row: sqlite3.Row, include_results: bool = True) -> Dict[str, Any]:
    record = dict(row)
    for column, target, default in (
        ("models_json", "models", []),
        ("summaries_json", "summaries", []),
        ("results_json", "results", []),
    ):
        raw = record.pop(column, None)
        try:
            record[target] = json.loads(raw) if raw else default
        except (json.JSONDecodeError, TypeError):
            record[target] = default
    if not include_results:
        record.pop("results", None)
    return record


def get_benchmark(run_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM benchmark_runs WHERE run_id = ?", (run_id,)).fetchone()
    return _restore_benchmark(row) if row else None


def list_benchmarks(limit: int = 20) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM benchmark_runs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_restore_benchmark(row, include_results=False) for row in rows]
