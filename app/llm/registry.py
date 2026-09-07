"""Provider registry and the single entry point every tool calls.

Routing is strict: the provider and model chosen in the UI are the source of
truth. There is no silent cross provider fallback, so a quota error from the
selected provider surfaces to the user with an actionable hint. Transient
errors are retried on the same provider only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from . import keyring
from .base import BaseProvider, ImagePart, LLMError, coerce_json
from .providers import (
    CloudflareProvider,
    GeminiProvider,
    GroqProvider,
    HuggingFaceProvider,
    OpenAIProvider,
)

# Display order in the picker.
_ORDER: tuple[type[BaseProvider], ...] = (
    GeminiProvider,
    GroqProvider,
    CloudflareProvider,
    OpenAIProvider,
    HuggingFaceProvider,
)

_registry: dict[str, BaseProvider] | None = None


def provider_map() -> dict[str, BaseProvider]:
    global _registry
    if _registry is None:
        _registry = {}
        for cls in _ORDER:
            instance = cls()
            _registry[instance.id] = instance
    return _registry


def reset_registry() -> None:
    """Rebuild adapters, used after the environment changes in tests."""
    global _registry
    _registry = None


def all_status() -> list[dict[str, Any]]:
    return [provider.status().as_dict() for provider in provider_map().values()]


def server_providers() -> list[str]:
    """Providers the deployment itself holds a key for, ignoring the request."""
    return [p.id for p in provider_map().values() if p.has_server_key()]


def client_providers() -> list[str]:
    """Providers the current request brought its own key for."""
    supplied = keyring.supplied()
    return [p.id for p in provider_map().values() if p.id in supplied]


def available_providers() -> list[BaseProvider]:
    return [p for p in provider_map().values() if p.is_available()]


def any_available() -> bool:
    return bool(available_providers())


def default_selection(vision: bool = False) -> tuple[str, str]:
    """First usable provider and model, used when the client sends nothing."""
    for provider in available_providers():
        model = provider.default_vision_model() if vision else provider.default_model()
        if model:
            return provider.id, model
    return "", ""


@dataclass
class Selection:
    provider: BaseProvider
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider.label} / {self.model}"


def resolve(
    provider_id: str | None = None,
    model: str | None = None,
    *,
    vision: bool = False,
) -> Selection:
    """Turn a client supplied provider and model into a usable Selection."""
    providers = provider_map()
    usable = available_providers()

    if not usable:
        raise LLMError(
            "No AI provider key is available for this request.",
            hint=(
                "Open Settings and paste your own API key for Google Gemini, Groq, "
                "Cloudflare Workers AI, OpenAI or Hugging Face. The key stays in "
                "your browser and is sent only with your own requests."
            ),
        )

    provider_id = (provider_id or "").strip().lower()
    model = (model or "").strip()

    if provider_id:
        provider = providers.get(provider_id)
        if provider is None:
            raise LLMError(
                f"Unknown provider '{provider_id}'.",
                hint=f"Available providers: {', '.join(p.id for p in usable)}.",
            )
        if not provider.is_available():
            raise LLMError(
                f"{provider.label} is not configured on this server.",
                provider=provider.id,
                hint=provider.unavailable_reason(),
            )
    else:
        provider = usable[0]

    if not model:
        model = provider.default_vision_model() if vision else provider.default_model()

    if vision and not provider.supports_vision(model):
        vision_model = provider.default_vision_model()
        if vision_model:
            model = vision_model
        else:
            vision_capable = [p.label for p in usable if p.supports_vision()]
            if len(vision_capable) > 1:
                names = ", ".join(vision_capable[:-1]) + " or " + vision_capable[-1]
            else:
                names = vision_capable[0] if vision_capable else ""
            raise LLMError(
                f"{provider.label} has no vision model configured, so it cannot read "
                "scanned pages.",
                provider=provider.id,
                hint=(
                    f"Switch to {names} in the model picker for this document."
                    if names
                    else "Add a provider with a vision model to process scanned documents."
                ),
            )

    if not model:
        raise LLMError(
            f"No model available for {provider.label}.",
            provider=provider.id,
            hint="Set a model id in the picker or through the environment.",
        )

    return Selection(provider=provider, model=model)


def generate(
    prompt: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    system: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    selection = resolve(provider, model)
    return selection.provider.generate(
        prompt,
        model=selection.model,
        system=system,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def generate_json(
    prompt: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    system: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    schema_hint: str = "",
) -> Any:
    """Ask for JSON and parse it defensively.

    Providers differ in how well they honour a JSON mode, so the schema is
    always described in the prompt and the response is parsed leniently.
    """
    selection = resolve(provider, model)
    full_system = system or ""
    if schema_hint:
        full_system = (
            f"{full_system}\n\nReturn JSON matching this shape exactly:\n{schema_hint}"
        ).strip()

    raw = selection.provider.generate(
        prompt,
        model=selection.model,
        system=full_system,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=True,
    )
    try:
        return coerce_json(raw)
    except ValueError as exc:
        raise LLMError(
            str(exc),
            provider=selection.provider.id,
            model=selection.model,
            hint=(
                "The selected model did not return structured output. "
                "A larger model usually fixes this."
            ),
        ) from exc


def vision(
    images: Sequence[ImagePart],
    prompt: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 4096,
) -> str:
    selection = resolve(provider, model, vision=True)
    return selection.provider.vision(
        images,
        prompt,
        model=selection.model,
        system=system,
        max_tokens=max_tokens,
    )


def supports_vision(provider_id: str | None, model: str | None = None) -> bool:
    provider = provider_map().get((provider_id or "").strip().lower())
    if provider is None or not provider.is_available():
        return False
    return provider.supports_vision(model or None)
