import json
import time
import logging
from abc import ABC, abstractmethod

from app.config import (
    LLM_PROVIDER,
    GROQ_API_KEY,
    GROQ_MODEL,
    GOOGLE_API_KEY,
    GEMINI_MODEL,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_WAIT_SECONDS = 5


def _clean_json_response(raw: str) -> dict:
    """Extract and parse JSON from an LLM response that may contain markdown fences."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    return json.loads(cleaned)


class BaseLLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, temperature: float = 0.3) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


class GroqProvider(BaseLLMProvider):
    def __init__(self):
        from groq import Groq
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not set. Get a free key at https://console.groq.com")
        self.client = Groq(api_key=GROQ_API_KEY)
        self.model = GROQ_MODEL
        logger.info(f"Groq provider ready (model: {self.model})")

    @property
    def name(self) -> str:
        return f"Groq/{self.model}"

    def generate(self, prompt: str, temperature: float = 0.3) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=4096,
        )
        return response.choices[0].message.content


class GeminiProvider(BaseLLMProvider):
    def __init__(self):
        import google.generativeai as genai
        if not GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY is not set. Get a key at https://aistudio.google.com/apikey")
        genai.configure(api_key=GOOGLE_API_KEY)
        self._genai = genai
        self.model = genai.GenerativeModel(GEMINI_MODEL)
        logger.info(f"Gemini provider ready (model: {GEMINI_MODEL})")

    @property
    def name(self) -> str:
        return f"Gemini/{GEMINI_MODEL}"

    def generate(self, prompt: str, temperature: float = 0.3) -> str:
        response = self.model.generate_content(
            prompt,
            generation_config=self._genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=4096,
            ),
        )
        return response.text


def _build_providers() -> list[BaseLLMProvider]:
    """Build an ordered list of LLM providers with automatic fallback.

    Priority logic:
    - If LLM_PROVIDER is set, try that first, then the other as fallback.
    - If a provider's API key is missing, it's silently skipped.
    - At least one provider must be available or the app won't start.
    """
    providers = []
    errors = []

    primary = LLM_PROVIDER.lower().strip()

    if primary == "groq":
        order = [("groq", GroqProvider, GROQ_API_KEY), ("gemini", GeminiProvider, GOOGLE_API_KEY)]
    else:
        order = [("gemini", GeminiProvider, GOOGLE_API_KEY), ("groq", GroqProvider, GROQ_API_KEY)]

    for label, cls, key in order:
        if not key:
            logger.info(f"Skipping {label} provider (no API key configured)")
            continue
        try:
            providers.append(cls())
        except Exception as e:
            errors.append(f"{label}: {e}")
            logger.warning(f"Could not initialize {label} provider: {e}")

    if not providers:
        raise ValueError(
            f"No LLM provider available. Configure at least one API key in .env:\n"
            f"  - GROQ_API_KEY (free at https://console.groq.com) [recommended]\n"
            f"  - GOOGLE_API_KEY (free at https://aistudio.google.com/apikey)\n"
            f"Init errors: {'; '.join(errors)}"
        )

    return providers


class LLMService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.providers = _build_providers()
        primary = self.providers[0].name
        fallbacks = [p.name for p in self.providers[1:]]
        logger.info(f"LLM service ready | Primary: {primary} | Fallbacks: {fallbacks or 'none'}")
        self._initialized = True

    def generate(self, prompt: str, temperature: float = 0.3) -> str:
        """Generate a response, trying each provider with short retries."""
        all_errors = []

        for provider in self.providers:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    logger.info(f"Calling {provider.name} (attempt {attempt})")
                    return provider.generate(prompt, temperature)
                except Exception as e:
                    err_str = str(e).lower()
                    is_rate_limit = any(k in err_str for k in ("429", "rate", "quota", "limit", "resource"))
                    all_errors.append(f"{provider.name}: {e}")

                    if is_rate_limit and attempt < MAX_RETRIES:
                        logger.warning(f"{provider.name} rate limited (attempt {attempt}), retrying in {RETRY_WAIT_SECONDS}s")
                        time.sleep(RETRY_WAIT_SECONDS)
                    elif is_rate_limit:
                        logger.warning(f"{provider.name} rate limited, trying next provider")
                        break
                    else:
                        logger.error(f"{provider.name} error: {e}")
                        break

        raise RuntimeError(
            f"All LLM providers failed. Errors: {'; '.join(all_errors)}"
        )

    def generate_json(self, prompt: str, temperature: float = 0.2) -> dict:
        """Generate a structured JSON response."""
        full_prompt = (
            f"{prompt}\n\n"
            "IMPORTANT: Respond ONLY with valid JSON. No markdown, no code fences, "
            "no explanation outside the JSON object."
        )
        raw = self.generate(full_prompt, temperature=temperature)
        return _clean_json_response(raw)

    def get_provider_info(self) -> dict:
        return {
            "primary": self.providers[0].name,
            "fallbacks": [p.name for p in self.providers[1:]],
            "total_providers": len(self.providers),
        }


def get_llm_service() -> LLMService:
    return LLMService()
