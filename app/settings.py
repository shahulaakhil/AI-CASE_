"""Central configuration. Every secret is read from the environment.

Nothing here raises at import time. A missing key simply means the matching
provider is reported as unavailable, so the app boots and runs with whatever
subset of keys is present.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"

# Only this project's own .env is read, and only to fill in variables the real
# environment has not already set. A hosted deployment has no .env at all, so
# the platform's environment is the single source of truth there.
# Set LITIGATAI_IGNORE_DOTENV=1 to skip the file entirely, which is useful when
# testing what a deployment with one specific key behaves like.
if os.environ.get("LITIGATAI_IGNORE_DOTENV", "").strip().lower() not in {"1", "true", "yes"}:
    _env_file = BASE_DIR / ".env"
    if _env_file.exists():
        load_dotenv(_env_file, override=False)


def env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return default


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


APP_NAME = env("APP_NAME", default="AI Case Intelligent")
APP_TAGLINE = env(
    "APP_TAGLINE",
    default="AI Case Intelligence for Indian litigation practice",
)
ENVIRONMENT = env("ENVIRONMENT", default="production")
DEBUG = env_bool("DEBUG", False)

# Provider credentials
GOOGLE_API_KEY = env("GOOGLE_API_KEY", "GEMINI_API_KEY")
GROQ_API_KEY = env("GROQ_API_KEY")
OPENAI_API_KEY = env("OPENAI_API_KEY")
OPENAI_BASE_URL = env("OPENAI_BASE_URL", default="https://api.openai.com/v1")
EMBEDDING_MODEL = env(
    "EMBEDDING_MODEL", default="sentence-transformers/all-MiniLM-L6-v2"
)
HUGGINGFACE_API_KEY = env(
    "HUGGINGFACE_API_KEY", "HUGGINGFACE_API_TOKEN", "HF_TOKEN", "HF_API_KEY"
)
HUGGINGFACE_BASE_URL = env(
    "HUGGINGFACE_BASE_URL", "HF_BASE_URL", default="https://router.huggingface.co/v1"
)

# Cloudflare Workers AI. Unlike the others this needs two values, because the
# account id is part of the URL path rather than a header, so a token on its
# own cannot address anything.
CLOUDFLARE_API_TOKEN = env(
    "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_API_KEY", "CF_API_TOKEN"
)
CLOUDFLARE_ACCOUNT_ID = env("CLOUDFLARE_ACCOUNT_ID", "CF_ACCOUNT_ID")

# Optional default model overrides
GEMINI_MODEL = env("GEMINI_MODEL")
GROQ_MODEL = env("GROQ_MODEL")
OPENAI_MODEL = env("OPENAI_MODEL")
HUGGINGFACE_MODEL = env("HUGGINGFACE_MODEL", "HF_MODEL")
CLOUDFLARE_MODEL = env("CLOUDFLARE_MODEL", "CF_MODEL")

# Optional extra models, comma separated, appended to the picker for a provider
EXTRA_MODELS = {
    "gemini": env("GEMINI_EXTRA_MODELS", default=""),
    "groq": env("GROQ_EXTRA_MODELS", default=""),
    "openai": env("OPENAI_EXTRA_MODELS", default=""),
    "huggingface": env("HUGGINGFACE_EXTRA_MODELS", default=""),
    "cloudflare": env("CLOUDFLARE_EXTRA_MODELS", default=""),
}

# Third party data sources
INDIAN_KANOON_API_TOKEN = env("INDIAN_KANOON_API_TOKEN", "KANOON_API_TOKEN")

# Bring your own key. When on, a visitor can paste their own provider key in
# the UI and it is sent with their requests only, which is what lets this app
# be hosted publicly without the operator paying for anyone's inference.
# Set ALLOW_CLIENT_KEYS=0 for a private deployment that must use only its own
# server side keys.
ALLOW_CLIENT_KEYS = env_bool("ALLOW_CLIENT_KEYS", True)

# Demo data. On a host with an ephemeral disk the tracker starts empty on every
# restart, which makes the case tracker look broken rather than new. When this
# is on, a few sample matters are inserted at start up, but only into a tracker
# that is already empty.
DEMO_SEED = env_bool("DEMO_SEED", False)

# Storage
DATABASE_URL = env("DATABASE_URL")
DATA_DIR = Path(env("DATA_DIR", default=str(BASE_DIR / "data")))
SQLITE_PATH = Path(env("SQLITE_PATH", default=str(DATA_DIR / "litigatai.db")))
BARE_ACTS_FILE = Path(env("BARE_ACTS_FILE", default=str(DATA_DIR / "bare_acts_data.json")))

# Limits
MAX_UPLOAD_MB = env_int("MAX_UPLOAD_MB", 25)
MAX_OCR_PAGES = env_int("MAX_OCR_PAGES", 8)
REQUEST_TIMEOUT = env_int("REQUEST_TIMEOUT", 180)
CORS_ORIGINS = env("CORS_ORIGINS", default="")

DATA_DIR.mkdir(parents=True, exist_ok=True)
