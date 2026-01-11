"""OpenAI LLM client adapter."""

import json
from typing import Any

from openai import AsyncOpenAI

from app.adapters.llm.base import AbstractLLMClient


class OpenAIClient(AbstractLLMClient):
    """Client for calling OpenAI chat completions and returning JSON.
    
    Uses the official OpenAI Python SDK with async support.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float = 45.0,
    ) -> None:
        """Initialize OpenAI async client.

        Args:
            api_key: OpenAI API key for authentication.
            model: Model name (e.g., "gpt-4o", "gpt-4o-mini").
            base_url: Optional custom base URL for OpenAI API.
            timeout_seconds: Timeout for requests in seconds.
        """
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
        )
        self.model = model

    async def generate_json(
        self,
        prompt: str,
        *,
        schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate structured JSON using OpenAI chat completions.

        Args:
            prompt: User prompt to send to the model.
            schema: Optional JSON schema to enforce (uses json_object mode if provided).
            **kwargs: Provider options (temperature, max_tokens, top_p, etc.).

        Returns:
            dict[str, Any]: Parsed JSON object from the LLM response.

        Raises:
            RuntimeError: If the API call fails or the response is not valid JSON.
        """
        # Build request parameters
        messages = [
            {
                "role": "system",
                "content": "Output JSON only. No extra text or markdown formatting.",
            },
            {"role": "user", "content": prompt},
        ]

        # Extract temperature with sensible default for JSON generation
        temperature = kwargs.pop("temperature", 0.2)

        # Build the request dict dynamically
        request_params: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        # Enforce JSON response format when schema is provided
        if schema is not None:
            request_params["response_format"] = {"type": "json_object"}

        # Pass through additional parameters if provided
        allowed_params = {
            "max_tokens",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "seed",
        }
        for param in allowed_params:
            if param in kwargs:
                request_params[param] = kwargs[param]

        try:
            response = await self.client.chat.completions.create(**request_params)
            content = response.choices[0].message.content
            
            if content is None:
                raise RuntimeError("LLM returned empty response")
            
            content = content.strip()
            
        except Exception as exc:
            raise RuntimeError(f"OpenAI API error: {str(exc)}") from exc

        # Parse and validate JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"LLM returned invalid JSON: {str(exc)}; "
                "consider using stricter prompts or schema enforcement"
            ) from exc
