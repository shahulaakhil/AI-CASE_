"""Provider-neutral contracts for the LLM layer."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from . import keyring

# A single global style rule appended to every system prompt so that generated
# legal text stays consistent regardless of which provider answers.
STYLE_RULES = (
    "Formatting rules that override any other style preference:\n"
    "1. Never use em dashes or en dashes. Use a comma, a colon, a full stop, "
    "or the word 'to' for ranges.\n"
    "2. Use plain ASCII punctuation throughout.\n"
    "3. Do not open a reply with filler such as 'Certainly' or 'Of course'."
)


class LLMError(RuntimeError):
    """Raised when a provider call cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        model: str = "",
        status: int | None = None,
        retryable: bool = False,
        hint: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.model = model
        self.status = status
        self.retryable = retryable
        self.hint = hint

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "retryable": self.retryable,
            "hint": self.hint,
        }


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    vision: bool = False
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "vision": self.vision, "note": self.note}


@dataclass
class ImagePart:
    data: bytes
    mime_type: str = "image/png"


@dataclass
class ProviderStatus:
    id: str
    label: str
    available: bool
    reason: str = ""
    models: Sequence[ModelSpec] = field(default_factory=tuple)
    default_model: str = ""
    docs_url: str = ""
    key_names: Sequence[str] = field(default_factory=tuple)
    # "client" when this request supplied the key, "server" when the key comes
    # from the deployment's environment, "" when there is no key at all.
    key_source: str = ""
    # True when the provider needs a second value alongside the key, which
    # Cloudflare does because its account id sits in the URL path. The key
    # panel renders an extra field for these.
    needs_account: bool = False
    # Whether that second value is present for this request.
    has_account: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "available": self.available,
            "reason": self.reason,
            "models": [m.as_dict() for m in self.models],
            "default_model": self.default_model,
            "docs_url": self.docs_url,
            "key_names": list(self.key_names),
            "has_vision": any(m.vision for m in self.models),
            "key_source": self.key_source,
            "needs_account": self.needs_account,
            "has_account": self.has_account,
        }


_FENCE_RE = re.compile(r"^```(?:json|JSON)?\s*|\s*```$")

# Models ignore style instructions often enough that the rule is also enforced
# here, on every response, before anything reaches the user or a document.
# En dash, em dash, figure dash and horizontal bar, built from code points so
# that no source file in this project contains one of these characters itself.
_DASH = "".join(chr(code) for code in (0x2013, 0x2014, 0x2012, 0x2015))
_RANGE_DASH_RE = re.compile(rf"(?<=\d)\s*[{_DASH}]\s*(?=\d)")
_LEADING_DASH_RE = re.compile(rf"(?m)^([ \t]*)[{_DASH}][ \t]+")
_SPACED_DASH_RE = re.compile(rf"[ \t]+[{_DASH}][ \t]+")
_ANY_DASH_RE = re.compile(rf"[{_DASH}]")
_DOUBLE_PUNCT_RE = re.compile(r"([,;:])[ \t]*,[ \t]+")


def sanitise_output(text: str) -> str:
    """Replace typographic dashes with plain ASCII punctuation.

    A range between numbers becomes "to", a dash used as a sentence break
    becomes a comma, a dash opening a line becomes a list hyphen, and anything
    left over becomes a hyphen.
    """
    if not text:
        return text
    cleaned = _RANGE_DASH_RE.sub(" to ", text)
    cleaned = _LEADING_DASH_RE.sub(lambda m: m.group(1) + "- ", cleaned)
    cleaned = _SPACED_DASH_RE.sub(", ", cleaned)
    cleaned = _ANY_DASH_RE.sub("-", cleaned)
    cleaned = _DOUBLE_PUNCT_RE.sub(lambda m: m.group(1) + " ", cleaned)
    return cleaned


def coerce_json(raw: str) -> Any:
    """Parse model output that is meant to be JSON but may carry noise.

    Handles bare JSON, fenced JSON, and JSON embedded inside prose.
    """
    if raw is None:
        raise ValueError("Model returned no content.")
    text = raw.strip()
    if not text:
        raise ValueError("Model returned an empty response.")

    text = _FENCE_RE.sub("", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Locate the outermost JSON object or array in the response.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    raise ValueError(f"Model did not return valid JSON. First 300 characters: {text[:300]!r}")


class BaseProvider:
    """Interface every provider adapter implements.

    An adapter is a process wide singleton, so the credential cannot live on
    the instance. `api_key` prefers the key the current request brought and
    falls back to the one the deployment holds in its environment, which makes
    the same object serve a bring your own key visitor and a server key
    deployment without either knowing about the other.
    """

    id: str = ""
    label: str = ""
    docs_url: str = ""
    key_names: tuple[str, ...] = ()
    models: tuple[ModelSpec, ...] = ()

    # Credential read from the environment at construction. May be None.
    env_key: str | None = None

    # Set by an adapter that needs a second value besides the key.
    needs_account: bool = False

    @property
    def account_id(self) -> str:
        """Only meaningful for an adapter that sets needs_account."""
        return ""

    @property
    def api_key(self) -> str | None:
        return keyring.key_for(self.id) or self.env_key

    @property
    def key_source(self) -> str:
        if keyring.key_for(self.id):
            return "client"
        return "server" if self.env_key else ""

    def has_server_key(self) -> bool:
        return bool(self.env_key)

    def is_available(self) -> bool:  # pragma: no cover - trivial
        raise NotImplementedError

    def unavailable_reason(self) -> str:
        return (
            f"Paste a {self.label} API key in Settings, or set "
            f"{' or '.join(self.key_names)} on the server."
        )

    def default_model(self) -> str:
        return self.models[0].id if self.models else ""

    def default_vision_model(self) -> str:
        for model in self.models:
            if model.vision:
                return model.id
        return ""

    def supports_vision(self, model: str | None = None) -> bool:
        if model is None:
            return any(m.vision for m in self.models)
        for spec in self.models:
            if spec.id == model:
                return spec.vision
        # Unknown custom model: assume the provider default capability.
        return any(m.vision for m in self.models)

    def status(self) -> ProviderStatus:
        available = self.is_available()
        return ProviderStatus(
            id=self.id,
            label=self.label,
            available=available,
            reason="" if available else self.unavailable_reason(),
            models=self.models if available else (),
            default_model=self.default_model() if available else "",
            docs_url=self.docs_url,
            key_names=self.key_names,
            key_source=self.key_source,
            needs_account=self.needs_account,
            has_account=bool(self.account_id),
        )

    def verify(self) -> list[str]:
        """Check the credential against the provider and list callable models."""
        raise NotImplementedError

    # The two calls every adapter must implement.
    def generate(
        self,
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def vision(
        self,
        images: Sequence[ImagePart],
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:  # pragma: no cover - interface
        raise NotImplementedError
