from abc import ABC, abstractmethod
from typing import Any


class AbstractLLMClient(ABC):
	"""Interface for LLM clients that produce structured JSON outputs."""

	@abstractmethod
	async def generate_json(
		self,
		prompt: str,
		*,
		schema: dict[str, Any] | None = None,
		**kwargs: Any,
	) -> dict[str, Any]:
		"""Generate a structured JSON response from the model.

		Args:
			prompt: User or system prompt to send to the model.
			schema: Optional JSON schema to validate/enforce on the response.
			**kwargs: Provider-specific options (e.g., temperature, max_tokens).

		Returns:
			dict[str, Any]: Parsed JSON object returned by the model.

		Raises:
			RuntimeError: If the provider call fails or the response cannot be parsed/validated.
		"""
		...
