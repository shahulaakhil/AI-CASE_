"""Concrete provider adapters: Gemini, Groq, OpenAI, Hugging Face.

Groq, OpenAI and Hugging Face all expose an OpenAI compatible chat completions
endpoint, so they share one adapter with different base URLs. Gemini uses the
google-genai SDK.
"""
from __future__ import annotations

import base64
import json
import re
import time
from typing import Any, Sequence

from .. import settings
from . import keyring
from .base import BaseProvider, ImagePart, LLMError, ModelSpec, STYLE_RULES, sanitise_output

# Model catalogues move fast, so every adapter asks its provider what it can
# actually serve and merges that with a curated list. Discovery is cached for
# the lifetime of the process, and a failure simply leaves the curated list.
_DISCOVERY_TTL = 900.0
_discovered: dict[str, tuple[float, list[str]]] = {}

# Ids that are not chat models, or that would only confuse the picker.
_SKIP_MODEL = re.compile(
    r"whisper|tts|speech|audio|orpheus|guard|embed|rerank|moderation|image|dall|"
    r"sora|veo|imagen|video|transcribe|realtime|codex|search-|computer-use|"
    r"aqa|-tuning|gemma-3n|antigravity|customtools|nano-banana",
    re.IGNORECASE,
)

# Families listed first when a gateway offers more models than the picker shows.
_FAMILY_ORDER = (
    "llama", "qwen", "deepseek", "gpt", "gemini", "mistral", "mixtral", "gemma",
    "glm", "kimi", "command", "minimax", "nemotron", "phi", "granite", "hermes",
)


def _family_rank(model_id: str) -> tuple[int, int, str]:
    lowered = model_id.lower()
    rank = len(_FAMILY_ORDER)
    for index, family in enumerate(_FAMILY_ORDER):
        if family in lowered:
            rank = index
            break
    # Instruction tuned chat models before base or specialist variants.
    tuned = 0 if ("instruct" in lowered or "-it" in lowered or "chat" in lowered) else 1
    return (rank, tuned, lowered)

_VISION_HINT = re.compile(
    r"\bvl\b|vision|gemini|gpt-4o|gpt-4\.1|gpt-5|gpt-4-turbo|scout|maverick|"
    r"llava|pixtral|internvl|molmo|-vl-|multimodal|omni",
    re.IGNORECASE,
)

# Families worth surfacing when a gateway lists hundreds of models.
_GOOD_FAMILY = re.compile(
    r"llama|qwen|deepseek|mistral|mixtral|gemma|phi-|command|nemotron|olmo|"
    r"glm|kimi|minimax|hermes|granite|smol|gpt-oss|compound",
    re.IGNORECASE,
)


# Cache entries are keyed by provider plus a fingerprint of the credential, so
# one visitor's model list is never served to another visitor whose key can
# call a different set of models.
_CACHE_CAP = 64


def _cache_key(provider_id: str, api_key: str | None) -> str:
    return f"{provider_id}:{keyring.fingerprint(api_key)}"


def _cache_get(provider_id: str, api_key: str | None = None) -> list[str] | None:
    entry = _discovered.get(_cache_key(provider_id, api_key))
    if entry and (time.monotonic() - entry[0]) < _DISCOVERY_TTL:
        return entry[1]
    return None


def _cache_put(provider_id: str, ids: list[str], api_key: str | None = None) -> None:
    if len(_discovered) >= _CACHE_CAP:
        # Drop the oldest half rather than grow without bound when many
        # visitors each bring their own key.
        for stale in sorted(_discovered, key=lambda k: _discovered[k][0])[: _CACHE_CAP // 2]:
            _discovered.pop(stale, None)
    _discovered[_cache_key(provider_id, api_key)] = (time.monotonic(), ids)


def _looks_like_vision(model_id: str) -> bool:
    return bool(_VISION_HINT.search(model_id))

_TRANSIENT_MARKERS = (
    "429",
    "resource_exhausted",
    "rate limit",
    "rate_limit",
    "503",
    "unavailable",
    "overloaded",
    "timeout",
    "timed out",
    "502",
    "504",
)


def _is_transient(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _TRANSIENT_MARKERS)


_RETRY_AFTER_RE = re.compile(r"try again in\s*(\d+(?:\.\d+)?)\s*(ms|s|m)\b", re.IGNORECASE)
_RETRY_DELAY_RE = re.compile(r"retry[^0-9]{0,20}(\d+(?:\.\d+)?)\s*s", re.IGNORECASE)


def _retry_delay(message: str, attempt: int) -> float:
    """How long to wait before retrying, honouring the provider's own advice."""
    match = _RETRY_AFTER_RE.search(message)
    if match:
        value = float(match.group(1))
        unit = match.group(2).lower()
        seconds = value / 1000 if unit == "ms" else value * 60 if unit == "m" else value
        return min(seconds + 1.0, 45.0)
    match = _RETRY_DELAY_RE.search(message)
    if match:
        return min(float(match.group(1)) + 1.0, 45.0)
    return min(2.5 * (attempt + 1), 20.0)


# Models that spend output tokens on hidden reasoning before answering.
_REASONING_MODEL = re.compile(r"gpt-oss|qwen3|deepseek-r1|magistral|o1-|o3-|o4-", re.IGNORECASE)


def _hint_for(message: str, provider_label: str) -> str:
    lowered = message.lower()
    if "429" in lowered or "quota" in lowered or "rate limit" in lowered:
        return (
            f"{provider_label} rejected the call for rate or quota reasons. "
            "Quotas are counted per model, so another model in the picker often "
            "still works. Otherwise wait a moment or switch provider."
        )
    if "402" in lowered or "credit" in lowered or "billing" in lowered:
        return (
            f"The {provider_label} account has no credit left for inference. "
            "Top the account up, or switch to another provider in the model picker."
        )
    # A 403 often means the key is fine but the plan or a model agreement is
    # not, so those cases must not be reported as a bad key.
    if "not available on" in lowered or "model agreement" in lowered:
        return (
            f"Your {provider_label} account cannot call that model. It may need a paid "
            "plan, or a model agreement you have not accepted yet. Choose another model "
            "in the picker."
        )
    if "413" in lowered or "estimated number of input" in lowered:
        return (
            "That model's context window is too small for this request. Choose a model "
            "with a larger context, or send a shorter document."
        )
    if "408" in lowered or "request timeout" in lowered:
        return (
            f"{provider_label} timed out on that model. Try again, or pick a faster "
            "model in the picker."
        )
    if any(token in lowered for token in ("401", "403", "invalid api key", "unauthor")):
        return (
            f"The {provider_label} API key was rejected. Check that it is the whole key, "
            "that it is still active, and that it belongs to this provider."
        )
    if any(token in lowered for token in ("404", "not found", "does not exist", "decommission")):
        return (
            f"{provider_label} does not recognise that model id. "
            "Choose another model in the picker."
        )
    if "context" in lowered and "length" in lowered:
        return "The document is too long for this model. Try a model with a larger context window."
    return ""


def _content_text(content: Any) -> str:
    """Normalise a chat completion's content into text.

    The OpenAI schema types this as a string, but not every gateway obeys.
    Cloudflare returns an already parsed object for some models, and the
    multipart content form arrives as a list of blocks, so both are flattened
    back to text rather than being allowed to crash on .strip().
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (dict, list)):
        # A multipart reply is a list of blocks, each carrying its own text.
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text") or block.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            if parts:
                return "\n".join(parts)
        # Anything else is structured output that was meant to be JSON text.
        try:
            return json.dumps(content, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(content)
    return str(content)


def _compose_system(system: str | None) -> str:
    if system:
        return f"{system.strip()}\n\n{STYLE_RULES}"
    return STYLE_RULES


def _extra(provider_id: str) -> tuple[ModelSpec, ...]:
    raw = settings.EXTRA_MODELS.get(provider_id) or ""
    out: list[ModelSpec] = []
    for chunk in raw.split(","):
        model_id = chunk.strip()
        if model_id:
            out.append(ModelSpec(id=model_id, label=model_id, note="From environment"))
    return tuple(out)


def _promote(models: list[ModelSpec], preferred: str | None) -> tuple[ModelSpec, ...]:
    """Move an environment preferred model to the front of the list."""
    if not preferred:
        return tuple(models)
    preferred = preferred.strip()
    for index, spec in enumerate(models):
        if spec.id == preferred:
            return tuple([models[index]] + models[:index] + models[index + 1 :])
    # Unknown id supplied through the environment: trust it and list it first.
    return tuple(
        [ModelSpec(preferred, preferred, vision=True, note="From environment")] + models
    )


def _merge_catalogue(
    curated: list[ModelSpec],
    live_ids: list[str] | None,
    *,
    cap: int,
    families_only: bool = False,
) -> list[ModelSpec]:
    """Combine the curated list with what the provider says it can serve."""
    if live_ids is None:
        return curated

    live = set(live_ids)
    merged = [spec for spec in curated if spec.id in live]
    known = {spec.id for spec in merged}

    extras: list[str] = []
    for model_id in live_ids:
        if model_id in known or _SKIP_MODEL.search(model_id):
            continue
        if families_only and not _GOOD_FAMILY.search(model_id):
            continue
        extras.append(model_id)

    extras.sort(key=_family_rank)
    for model_id in extras:
        if len(merged) >= cap:
            break
        merged.append(
            ModelSpec(
                model_id,
                model_id.split("/")[-1],
                vision=_looks_like_vision(model_id),
                note="Offered by your account",
            )
        )

    # Never hand back an empty picker.
    return merged or curated


class OpenAICompatibleProvider(BaseProvider):
    """Shared adapter for any OpenAI compatible chat completions endpoint."""

    env_base_url: str = ""
    max_attempts: int = 3
    model_cap: int = 24
    families_only: bool = False
    curated: list[ModelSpec] = []
    preferred: str | None = None

    @property
    def base_url(self) -> str:
        """A visitor may point the adapter at their own compatible gateway."""
        return keyring.base_url_for(self.id) or self.env_base_url

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _discover(self) -> list[str]:
        """Ask the gateway which models this key can actually call."""
        api_key = self.api_key
        if not api_key:
            return []
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=self.base_url, timeout=12.0,
                            max_retries=0)
            return [item.id for item in client.models.list().data if getattr(item, "id", None)]
        except Exception:  # noqa: BLE001 - discovery is best effort
            return []

    @property
    def models(self) -> tuple[ModelSpec, ...]:
        api_key = self.api_key
        live = _cache_get(self.id, api_key)
        if live is None:
            live = self._discover()
            _cache_put(self.id, live, api_key)
        merged = _merge_catalogue(
            list(self.curated), live, cap=self.model_cap, families_only=self.families_only
        )
        return _promote(merged, self.preferred)

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise LLMError(
                "The openai package is not installed on the server.",
                provider=self.id,
            ) from exc
        if not self.api_key:
            raise LLMError(
                self.unavailable_reason(), provider=self.id, hint="Missing API key."
            )
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=float(settings.REQUEST_TIMEOUT),
            max_retries=0,
        )

    def verify(self) -> list[str]:
        """Prove the credential works, and report what it can call.

        A visitor who pastes a key needs to know straight away whether it is
        good, so this makes one real, unbilled request and lets the failure
        through instead of swallowing it the way discovery does.
        """
        if not self.api_key:
            raise LLMError(self.unavailable_reason(), provider=self.id)
        client = self._client()
        try:
            ids = [item.id for item in client.models.list().data if getattr(item, "id", None)]
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            message = str(exc)
            raise LLMError(
                f"{self.label} did not accept that key.",
                provider=self.id,
                hint=_hint_for(message, self.label),
            ) from exc
        _cache_put(self.id, ids, self.api_key)
        return ids

    def _call(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        client = self._client()
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if _REASONING_MODEL.search(model):
            # Reasoning models spend the output budget thinking. Keep that short
            # so the visible answer still fits, and give it more room.
            kwargs["reasoning_effort"] = "low"
            kwargs["max_tokens"] = max(max_tokens, 8192)

        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = client.chat.completions.create(**kwargs)
                choice = response.choices[0] if response.choices else None
                message_obj = choice.message if choice else None
                content = _content_text(
                    getattr(message_obj, "content", None) if message_obj else None
                )
                if content.strip():
                    return sanitise_output(content.strip())

                finish = (getattr(choice, "finish_reason", "") or "") if choice else ""
                if finish == "length":
                    raise RuntimeError(
                        "The model ran out of output tokens before it produced an answer. "
                        "This usually means a reasoning model spent the whole budget "
                        "thinking. Pick a non reasoning model, or a shorter input."
                    )
                if finish in ("content_filter", "safety"):
                    raise RuntimeError(
                        "The provider's safety filter blocked this response. "
                        "Rephrase the request or switch model."
                    )
                raise RuntimeError(
                    f"The model returned an empty response (finish reason: {finish or 'none'})."
                )
            except Exception as exc:  # noqa: BLE001 - normalised below
                message = str(exc)
                last_error = exc
                lowered = message.lower()
                # Some gateways reject json_object mode. Retry once without it.
                if json_mode and ("response_format" in lowered or "json_object" in lowered):
                    kwargs.pop("response_format", None)
                    json_mode = False
                    continue
                # Some gateways only accept max_completion_tokens.
                if "max_completion_tokens" in lowered and "max_tokens" in kwargs:
                    kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
                    continue
                if "temperature" in lowered and "unsupported" in lowered:
                    kwargs.pop("temperature", None)
                    continue
                if "reasoning_effort" in lowered and "reasoning_effort" in kwargs:
                    kwargs.pop("reasoning_effort", None)
                    continue
                if _is_transient(message) and attempt < self.max_attempts - 1:
                    time.sleep(_retry_delay(message, attempt))
                    continue
                break

        message = str(last_error) if last_error else "Unknown provider error."
        raise LLMError(
            f"{self.label} call failed: {message[:400]}",
            provider=self.id,
            model=model,
            retryable=_is_transient(message),
            hint=_hint_for(message, self.label),
        )

    def generate(
        self,
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:
        messages = [
            {"role": "system", "content": _compose_system(system)},
            {"role": "user", "content": prompt},
        ]
        if json_mode:
            messages[0]["content"] += (
                "\n\nReturn only a single valid JSON value. No prose, no markdown fences."
            )
        return self._call(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

    def vision(
        self,
        images: Sequence[ImagePart],
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image in images:
            encoded = base64.b64encode(image.data).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image.mime_type};base64,{encoded}"},
                }
            )
        messages = [
            {"role": "system", "content": _compose_system(system)},
            {"role": "user", "content": content},
        ]
        return self._call(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=False,
        )


class GroqProvider(OpenAICompatibleProvider):
    id = "groq"
    label = "Groq"
    docs_url = "https://console.groq.com/keys"
    key_names = ("GROQ_API_KEY",)
    env_base_url = "https://api.groq.com/openai/v1"
    model_cap = 20

    def __init__(self) -> None:
        self.env_key = settings.GROQ_API_KEY
        self.preferred = settings.GROQ_MODEL
        self.curated = [
            ModelSpec("openai/gpt-oss-120b", "GPT OSS 120B",
                      note="Strong reasoning, the best default here"),
            ModelSpec("openai/gpt-oss-20b", "GPT OSS 20B", note="Fastest"),
            ModelSpec("llama-3.3-70b-versatile", "Llama 3.3 70B Versatile"),
            ModelSpec("groq/compound", "Compound", note="Tool augmented"),
            ModelSpec("meta-llama/llama-4-scout-17b-16e-instruct", "Llama 4 Scout 17B",
                      vision=True, note="Reads scanned pages"),
            ModelSpec("meta-llama/llama-4-maverick-17b-128e-instruct", "Llama 4 Maverick 17B",
                      vision=True, note="Larger vision model"),
        ] + list(_extra(self.id))


class OpenAIProvider(OpenAICompatibleProvider):
    id = "openai"
    label = "OpenAI"
    docs_url = "https://platform.openai.com/api-keys"
    key_names = ("OPENAI_API_KEY",)
    model_cap = 22
    families_only = False

    def __init__(self) -> None:
        self.env_key = settings.OPENAI_API_KEY
        self.env_base_url = settings.OPENAI_BASE_URL or "https://api.openai.com/v1"
        self.preferred = settings.OPENAI_MODEL
        self.curated = [
            ModelSpec("gpt-4o-mini", "GPT-4o mini", vision=True, note="Fast and inexpensive"),
            ModelSpec("gpt-4o", "GPT-4o", vision=True, note="Highest quality drafting"),
            ModelSpec("gpt-4.1-mini", "GPT-4.1 mini", vision=True),
            ModelSpec("gpt-4.1", "GPT-4.1", vision=True, note="Large context"),
        ] + list(_extra(self.id))

    def unavailable_reason(self) -> str:
        return (
            "Paste an OpenAI API key in Settings, or set OPENAI_API_KEY on the server. "
            "Any OpenAI compatible gateway also works if you give its base URL."
        )


class HuggingFaceProvider(OpenAICompatibleProvider):
    id = "huggingface"
    label = "Hugging Face"
    docs_url = "https://huggingface.co/settings/tokens"
    key_names = ("HUGGINGFACE_API_KEY", "HF_TOKEN")
    model_cap = 30
    families_only = True

    def __init__(self) -> None:
        self.env_key = settings.HUGGINGFACE_API_KEY
        self.env_base_url = (
            settings.HUGGINGFACE_BASE_URL or "https://router.huggingface.co/v1"
        )
        self.preferred = settings.HUGGINGFACE_MODEL
        self.curated = [
            ModelSpec("meta-llama/Llama-3.3-70B-Instruct", "Llama 3.3 70B Instruct"),
            ModelSpec("Qwen/Qwen2.5-72B-Instruct", "Qwen2.5 72B Instruct"),
            ModelSpec("deepseek-ai/DeepSeek-V3-0324", "DeepSeek V3", note="Long context"),
            ModelSpec("Qwen/Qwen2.5-VL-7B-Instruct", "Qwen2.5 VL 7B", vision=True,
                      note="Reads scanned pages"),
        ] + list(_extra(self.id))

    def unavailable_reason(self) -> str:
        return (
            "Paste a Hugging Face access token in Settings, or set HUGGINGFACE_API_KEY "
            "on the server. Which models you can call depends on the account."
        )


# Cloudflare's REST root. The account id goes in the path, so the base URL
# cannot be a constant the way the other providers' are.
_CF_API_ROOT = "https://api.cloudflare.com/client/v4"


class CloudflareProvider(OpenAICompatibleProvider):
    """Cloudflare Workers AI, through its OpenAI compatible endpoint.

    Two things make this one different from the other three OpenAI protocol
    providers:

      * The account id is part of the URL, not a header, so a token alone is
        not enough and `is_available` has to check for both.
      * The OpenAI compatibility layer does not serve a models list, so
        discovery uses Cloudflare's own models/search endpoint instead.
    """

    id = "cloudflare"
    label = "Cloudflare Workers AI"
    docs_url = "https://dash.cloudflare.com/profile/api-tokens"
    key_names = ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")
    model_cap = 26
    needs_account = True

    def __init__(self) -> None:
        self.env_key = settings.CLOUDFLARE_API_TOKEN
        self.env_account = settings.CLOUDFLARE_ACCOUNT_ID
        self.preferred = settings.CLOUDFLARE_MODEL
        # Only ids verified against Cloudflare's own model pages are listed
        # here. Everything else the account can call arrives through discovery.
        self.curated = [
            ModelSpec(
                "@cf/openai/gpt-oss-120b",
                "GPT OSS 120B",
                note="128k context, strongest reasoning here",
            ),
            ModelSpec(
                "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
                "Llama 3.3 70B Instruct FP8 Fast",
                note="24k context, quick and capable default",
            ),
            ModelSpec(
                "@cf/meta/llama-4-scout-17b-16e-instruct",
                "Llama 4 Scout 17B",
                vision=True,
                note="131k context, natively multimodal, reads scanned pages",
            ),
            ModelSpec(
                "@cf/qwen/qwen3-30b-a3b-fp8",
                "Qwen3 30B A3B FP8",
                note="32k context",
            ),
        ] + list(_extra(self.id))

    @property
    def account_id(self) -> str:
        return keyring.account_for(self.id) or self.env_account or ""

    @property
    def base_url(self) -> str:
        override = keyring.base_url_for(self.id)
        if override:
            return override
        account = self.account_id
        if not account:
            return ""
        return f"{_CF_API_ROOT}/accounts/{account}/ai/v1"

    def is_available(self) -> bool:
        return bool(self.api_key and self.account_id)

    def unavailable_reason(self) -> str:
        if self.api_key and not self.account_id:
            return (
                "Cloudflare needs an account id as well as a token, because the "
                "account is part of the request URL. Add it in Settings, or set "
                "CLOUDFLARE_ACCOUNT_ID on the server."
            )
        if self.account_id and not self.api_key:
            return (
                "An account id is set but no token. Paste a Cloudflare API token "
                "in Settings, or set CLOUDFLARE_API_TOKEN on the server."
            )
        return (
            "Paste a Cloudflare API token and your account id in Settings, or set "
            "CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID on the server. Both "
            "are needed: the account id goes in the request URL."
        )

    def _discover(self) -> list[str]:
        """Ask Cloudflare which text generation models this account can call.

        The OpenAI compatibility layer has no /models route, so this uses the
        native catalogue and keeps only chat capable ids.
        """
        token = self.api_key
        account = self.account_id
        if not (token and account):
            return []
        try:
            import requests

            response = requests.get(
                f"{_CF_API_ROOT}/accounts/{account}/ai/models/search",
                params={
                    "task": "Text Generation",
                    "per_page": 100,
                    "hide_experimental": "true",
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("success"):
                return []
            ids: list[str] = []
            for item in payload.get("result") or []:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("id") or ""
                # Workers AI ids are namespaced. Anything else is not callable
                # through the chat completions route.
                if isinstance(name, str) and name.startswith(("@cf/", "@hf/")):
                    ids.append(name)
            return ids
        except Exception:  # noqa: BLE001 - discovery is best effort
            return []

    def verify(self) -> list[str]:
        """Prove the token and account id work together.

        The compatibility layer has no models route, so the catalogue call is
        the cheapest authenticated request that proves both halves are right.
        """
        token = self.api_key
        account = self.account_id
        if not (token and account):
            raise LLMError(self.unavailable_reason(), provider=self.id)
        try:
            import requests

            response = requests.get(
                f"{_CF_API_ROOT}/accounts/{account}/ai/models/search",
                params={"task": "Text Generation", "per_page": 100,
                        "hide_experimental": "true"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMError(
                "Cloudflare could not be reached.",
                provider=self.id,
                hint=str(exc)[:200],
            ) from exc

        if response.status_code in (401, 403):
            raise LLMError(
                "Cloudflare rejected that token for this account.",
                provider=self.id,
                hint=(
                    "Check that the token has the Workers AI Read permission and "
                    "that the account id belongs to the same account as the token."
                ),
            )
        if response.status_code == 404:
            raise LLMError(
                "Cloudflare did not recognise that account id.",
                provider=self.id,
                hint=(
                    "Copy the Account ID from the Cloudflare dashboard overview "
                    "page. It is 32 hexadecimal characters."
                ),
            )
        if response.status_code >= 400:
            raise LLMError(
                f"Cloudflare returned {response.status_code}.",
                provider=self.id,
                hint=response.text[:200],
            )

        ids = self._discover()
        if not ids:
            raise LLMError(
                "The token and account worked, but no text generation model was "
                "returned for this account.",
                provider=self.id,
                hint="Enable Workers AI on the account, then try again.",
            )
        _cache_put(self.id, ids, f"{self.api_key}:{account}")
        return ids

    @property
    def models(self) -> tuple[ModelSpec, ...]:
        # Cached per token AND account, since either can change the answer.
        tag = f"{self.api_key}:{self.account_id}"
        live = _cache_get(self.id, tag)
        if live is None:
            live = self._discover()
            _cache_put(self.id, live, tag)
        merged = _merge_catalogue(list(self.curated), live, cap=self.model_cap)
        return _promote(merged, self.preferred)


class GeminiProvider(BaseProvider):
    id = "gemini"
    label = "Google Gemini"
    docs_url = "https://aistudio.google.com/apikey"
    key_names = ("GOOGLE_API_KEY", "GEMINI_API_KEY")
    max_attempts = 3

    model_cap = 18

    def __init__(self) -> None:
        self.env_key = settings.GOOGLE_API_KEY
        self.preferred = settings.GEMINI_MODEL
        self.curated = [
            ModelSpec(
                "gemini-2.5-flash",
                "Gemini 2.5 Flash",
                vision=True,
                note="Balanced default, reads scanned pages",
            ),
            ModelSpec("gemini-2.5-pro", "Gemini 2.5 Pro", vision=True, note="Deepest reasoning"),
            ModelSpec(
                "gemini-2.5-flash-lite",
                "Gemini 2.5 Flash Lite",
                vision=True,
                note="Fastest and cheapest",
            ),
            ModelSpec("gemini-2.0-flash", "Gemini 2.0 Flash", vision=True),
        ] + list(_extra(self.id))
        # One SDK client per credential, never one per adapter, so a visitor's
        # key can never be reused for someone else's request.
        self._clients: dict[str, Any] = {}
        self._labels: dict[str, str] = {}

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _discover(self) -> list[str]:
        if not self.api_key:
            return []
        try:
            ids: list[str] = []
            for item in self._client().models.list():
                actions = getattr(item, "supported_actions", None) or []
                if "generateContent" not in actions:
                    continue
                name = self._normalise(getattr(item, "name", "") or "")
                if not name:
                    continue
                ids.append(name)
                display = getattr(item, "display_name", "") or ""
                if display:
                    self._labels[name] = display
            return ids
        except Exception:  # noqa: BLE001 - discovery is best effort
            return []

    @property
    def models(self) -> tuple[ModelSpec, ...]:
        api_key = self.api_key
        live = _cache_get(self.id, api_key)
        if live is None:
            live = self._discover()
            _cache_put(self.id, live, api_key)
        merged = _merge_catalogue(list(self.curated), live, cap=self.model_cap)
        # Every Gemini text model reads images, and the display names are good.
        merged = [
            ModelSpec(
                spec.id,
                self._labels.get(spec.id, spec.label),
                vision=True,
                note=spec.note,
            )
            for spec in merged
        ]
        return _promote(merged, self.preferred)

    def _client(self):
        api_key = self.api_key
        if not api_key:
            raise LLMError(self.unavailable_reason(), provider=self.id, hint="Missing API key.")
        tag = keyring.fingerprint(api_key)
        cached = self._clients.get(tag)
        if cached is not None:
            return cached
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise LLMError(
                "The google-genai package is not installed on the server.",
                provider=self.id,
            ) from exc
        if len(self._clients) >= 16:
            self._clients.clear()
        client = genai.Client(api_key=api_key)
        self._clients[tag] = client
        return client

    def verify(self) -> list[str]:
        """See OpenAICompatibleProvider.verify."""
        if not self.api_key:
            raise LLMError(self.unavailable_reason(), provider=self.id)
        client = self._client()
        try:
            ids: list[str] = []
            for item in client.models.list():
                name = self._normalise(getattr(item, "name", "") or "")
                actions = getattr(item, "supported_actions", None) or []
                if name and "generateContent" in actions:
                    ids.append(name)
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            message = str(exc)
            raise LLMError(
                f"{self.label} did not accept that key.",
                provider=self.id,
                hint=_hint_for(message, self.label),
            ) from exc
        _cache_put(self.id, ids, self.api_key)
        return ids

    @staticmethod
    def _normalise(model: str) -> str:
        model = (model or "").strip()
        return model[len("models/") :] if model.startswith("models/") else model

    def _config(self, *, system: str | None, temperature: float, max_tokens: int, json_mode: bool):
        from google.genai import types

        kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "system_instruction": _compose_system(system),
        }
        try:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except Exception:  # noqa: BLE001 - older SDKs lack thinking config
            pass
        if json_mode:
            kwargs["response_mime_type"] = "application/json"
        return types.GenerateContentConfig(**kwargs)

    def _run(
        self,
        contents: Any,
        *,
        model: str,
        system: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        client = self._client()
        model_name = self._normalise(model)
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                config = self._config(
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )
                response = client.models.generate_content(
                    model=model_name, contents=contents, config=config
                )
                text = sanitise_output((getattr(response, "text", "") or "").strip())
                if not text:
                    raise RuntimeError(
                        "Gemini returned an empty response. The prompt may have been blocked "
                        "by a safety filter, or the output token budget was too small."
                    )
                return text
            except Exception as exc:  # noqa: BLE001 - normalised below
                last_error = exc
                message = str(exc)
                if json_mode and "response_mime_type" in message:
                    json_mode = False
                    continue
                if _is_transient(message) and attempt < self.max_attempts - 1:
                    time.sleep(_retry_delay(message, attempt))
                    continue
                break

        message = str(last_error) if last_error else "Unknown provider error."
        raise LLMError(
            f"Gemini call failed: {message[:400]}",
            provider=self.id,
            model=model,
            retryable=_is_transient(message),
            hint=_hint_for(message, self.label),
        )

    def generate(
        self,
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:
        return self._run(
            prompt,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

    def vision(
        self,
        images: Sequence[ImagePart],
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        from google.genai import types

        parts: list[Any] = [
            types.Part.from_bytes(data=image.data, mime_type=image.mime_type) for image in images
        ]
        parts.append(prompt)
        return self._run(
            parts,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=False,
        )
