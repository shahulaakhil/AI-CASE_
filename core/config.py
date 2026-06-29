"""Env loading and project paths."""
from __future__ import annotations

import os
from pathlib import Path

try:
    import streamlit as st

    # When deployed on Streamlit Cloud
    for k, v in st.secrets.items():
        os.environ.setdefault(k, str(v))
except Exception:
    pass
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PARENT_DIR = PROJECT_ROOT.parent

for candidate in (PROJECT_ROOT / ".env", PARENT_DIR / ".env"):
    if candidate.exists():
        load_dotenv(candidate, override=False)


def _require(name: str, *aliases: str) -> str:
    for key in (name, *aliases):
        v = os.environ.get(key)
        if v:
            return v
    raise RuntimeError(f"Missing env var. Set one of: {[name, *aliases]} in .env")


def _optional(name: str, *aliases: str, default: str | None = None) -> str | None:
    for key in (name, *aliases):
        v = os.environ.get(key)
        if v:
            return v
    return default


GOOGLE_API_KEY = _require("GOOGLE_API_KEY", "GEMINI_API_KEY")
GROQ_API_KEY = _require("GROQ_API_KEY")
INDIAN_KANOON_API_TOKEN = _optional("INDIAN_KANOON_API_TOKEN")

GEMINI_MODEL = _optional("GEMINI_MODEL", default="gemini-2.5-flash")
GROQ_MODEL = _optional("GROQ_MODEL", default="llama-3.3-70b-versatile")

# Siemens OpenAI-compatible API (fallback when Gemini quota is exhausted)
SIEMENS_API_KEY = _optional("SIEMENS_API_KEY", "OPENAI_API_KEY")
SIEMENS_BASE_URL = _optional("SIEMENS_BASE_URL", default="https://api.siemens.com/llm/v1")
SIEMENS_MODEL = _optional("SIEMENS_MODEL", default="gpt-oss-120b-onprem")

DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
UPLOADS_DIR = PROJECT_ROOT / "uploads"

for d in (DATA_DIR, OUTPUT_DIR, UPLOADS_DIR):
    d.mkdir(parents=True, exist_ok=True)
