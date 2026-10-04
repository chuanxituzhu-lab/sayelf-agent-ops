from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ADAPTER_ID = "openai-compatible-chat-completions"
ADAPTER_VERSION = "1"


class ProviderError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def is_local_endpoint(endpoint: str) -> bool:
    try:
        return urlsplit(endpoint).hostname in {"localhost", "127.0.0.1", "::1"}
    except ValueError:
        return False


class OpenAICompatibleProvider:
    """Minimal, provider-neutral adapter for OpenAI-compatible chat endpoints."""

    adapter_id = ADAPTER_ID
    adapter_version = ADAPTER_VERSION

    def __init__(self, endpoint: str, model: str, api_key: str, timeout: int = 90, opener=None):
        if not endpoint or not model or not api_key:
            raise ProviderError("MODEL_NOT_CONFIGURED")
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = min(max(int(timeout), 5), 120)
        self.opener = opener or urlopen
        self.last_usage = None

    def complete_json(self, system_prompt: str, user_payload: dict) -> dict:
        self.last_usage = None
        body = json.dumps({
            "model": self.model,
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        }, ensure_ascii=False).encode("utf-8")
        if len(body) > 250_000:
            raise ProviderError("MODEL_INPUT_TOO_LARGE")
        request = Request(
            f"{self.endpoint}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                raw = response.read(1_000_001)
        except HTTPError as error:
            code = "MODEL_RATE_LIMITED" if error.code == 429 else "MODEL_REJECTED_REQUEST"
            raise ProviderError(code) from None
        except (TimeoutError, URLError, OSError):
            raise ProviderError("MODEL_UNAVAILABLE") from None
        if len(raw) > 1_000_000:
            raise ProviderError("MODEL_RESPONSE_TOO_LARGE")
        try:
            envelope = json.loads(raw.decode("utf-8"))
            usage = envelope.get("usage") if isinstance(envelope, dict) else None
            if isinstance(usage, dict):
                self.last_usage = {
                    key: usage[key]
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                    if isinstance(usage.get(key), int)
                    and not isinstance(usage.get(key), bool)
                    and 0 <= usage[key] <= 1_000_000_000
                }
            content = envelope["choices"][0]["message"]["content"]
            result = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError):
            raise ProviderError("MODEL_RESPONSE_INVALID") from None
        if not isinstance(result, dict):
            raise ProviderError("MODEL_RESPONSE_INVALID")
        return result
