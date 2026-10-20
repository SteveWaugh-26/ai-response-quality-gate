
from typing import Any, Dict, Optional

import httpx

from app.config import (
    DEFAULT_MODEL,
    OLLAMA_BASE_URL,
    REQUEST_TIMEOUT,
)


async def generate_response(
    prompt: str,
    model: Optional[str] = None,
    expected_schema: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a response using a local Ollama model."""

    selected_model = model or DEFAULT_MODEL

    payload: Dict[str, Any] = {
        "model": selected_model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }

    if expected_schema is not None:
        payload["format"] = expected_schema

    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"

    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT
        ) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

            try:
                data = response.json()
            except ValueError as exc:
                raise RuntimeError(
                    "Ollama returned an invalid JSON response."
                ) from exc

    except httpx.TimeoutException as exc:
        raise RuntimeError(
            f"Ollama request timed out after {REQUEST_TIMEOUT} seconds."
        ) from exc

    except httpx.ConnectError as exc:
        raise RuntimeError(
            "Cannot connect to Ollama. Check that Ollama is running "
            f"at {OLLAMA_BASE_URL}."
        ) from exc

    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Ollama returned HTTP {exc.response.status_code}: "
            f"{exc.response.text[:300]}"
        ) from exc

    except httpx.RequestError as exc:
        raise RuntimeError(
            f"An error occurred while communicating with Ollama: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            "Ollama returned an unexpected response format."
        )

    message = data.get("message")

    if not isinstance(message, dict):
        raise RuntimeError(
            "Ollama response does not contain a valid message."
        )

    content = message.get("content")

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama returned an empty response.")

    return content
