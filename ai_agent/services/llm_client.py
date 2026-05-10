"""
LLM client kompatibilní s OpenAI API formátem.
Funguje s Ollama (http://localhost:11434/v1) i OpenAI cloud API.
"""
import logging
import time
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_RETRY_DELAYS = (5, 15, 30)  # sekundy mezi pokusy


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int


class LLMClient:
    """
    Volá /v1/chat/completions endpoint.
    Nastavení přes settings.py:
      AI_AGENT_BASE_URL  – výchozí http://localhost:11434/v1  (Ollama)
      AI_AGENT_MODEL     – výchozí llama3.2
      AI_AGENT_API_KEY   – prázdný pro Ollama, OPENAI_API_KEY pro OpenAI
      AI_AGENT_TIMEOUT   – timeout v sekundách, výchozí 120
    """

    def __init__(self):
        self.base_url = getattr(settings, "AI_AGENT_BASE_URL", "http://localhost:11434/v1").rstrip("/")
        self.model = getattr(settings, "AI_AGENT_MODEL", "llama3.2")
        self.api_key = getattr(settings, "AI_AGENT_API_KEY", "") or ""
        self.timeout = getattr(settings, "AI_AGENT_TIMEOUT", 120)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> LLMResponse:
        """
        Odešle zprávu do modelu a vrátí odpověď.
        Při síťové chybě nebo HTTP 5xx zkusí 3× s prodlevou 5 / 15 / 30 s.
        HTTP 4xx (špatný požadavek, auth) se neopakuje.
        """
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "stream": False,
        }

        last_exc: Exception | None = None
        for attempt, delay in enumerate([0] + list(_RETRY_DELAYS), start=1):
            if delay:
                logger.warning("LLM retry %d/%d za %ds", attempt, len(_RETRY_DELAYS) + 1, delay)
                time.sleep(delay)

            start = time.monotonic()
            try:
                resp = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
            except requests.ConnectionError as exc:
                last_exc = exc
                logger.warning("LLM connection error (pokus %d): %s", attempt, exc)
                continue
            except requests.Timeout as exc:
                last_exc = exc
                logger.warning("LLM timeout (pokus %d)", attempt)
                continue
            except requests.RequestException as exc:
                # Ostatní síťové chyby – neopakovat
                logger.error("LLM request failed: %s", exc)
                raise

            elapsed_ms = int((time.monotonic() - start) * 1000)

            if resp.status_code >= 500:
                last_exc = requests.HTTPError(response=resp)
                logger.warning("LLM server error %s (pokus %d)", resp.status_code, attempt)
                continue

            # 4xx – chyba na naší straně, opakování nepomůže
            resp.raise_for_status()

            data = resp.json()
            choice = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            model_used = data.get("model", self.model)

            return LLMResponse(
                content=choice,
                model=model_used,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                duration_ms=elapsed_ms,
            )

        logger.error("LLM selhal po všech pokusech: %s", last_exc)
        raise last_exc

    def is_available(self) -> bool:
        """Rychlý test dostupnosti serveru."""
        try:
            resp = requests.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=5,
            )
            return resp.ok
        except requests.RequestException:
            return False
