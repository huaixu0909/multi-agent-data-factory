import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.core.config import BASE_DIR


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


@dataclass
class LLMGenerationResult:
    messages: list[dict[str, str]]
    provider: str
    model: str


class DeepSeekClient:
    provider = "deepseek"

    def __init__(self) -> None:
        load_local_env()
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL).strip().rstrip("/")
        self.model = os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL).strip()
        self.timeout = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "45"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def chat_object(self, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> dict:
        if not self.enabled:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"DeepSeek API HTTP {error.code}: {body[:500]}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"DeepSeek API request failed: {error.reason}") from error

        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
        return parse_json_object(content)

    def chat_json(self, system_prompt: str, user_prompt: str) -> LLMGenerationResult:
        parsed = self.chat_object(system_prompt, user_prompt, temperature=0.7)
        messages = parsed.get("messages")
        if not isinstance(messages, list):
            raise RuntimeError("DeepSeek response missing messages array")

        normalized: list[dict[str, str]] = []
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip()
            text = str(item.get("content", "")).strip()
            if role and text:
                normalized.append({"role": role, "content": text})

        if not normalized:
            raise RuntimeError("DeepSeek response contains no valid messages")

        return LLMGenerationResult(messages=normalized, provider=self.provider, model=self.model)


def load_local_env() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_json_object(content: str) -> dict:
    cleaned = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def build_deepseek_client() -> DeepSeekClient:
    return DeepSeekClient()
