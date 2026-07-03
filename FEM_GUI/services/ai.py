from __future__ import annotations


class AIService:
    def send(self, api_key: str, messages: list[dict[str, str]], system: str) -> str:
        try:
            import anthropic
        except ModuleNotFoundError as exc:
            raise RuntimeError("anthropic is not installed. Install FEM_GUI requirements.") from exc
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=system,
            messages=messages,
        )
        return response.content[0].text

