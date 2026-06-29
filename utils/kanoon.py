"""Indian Kanoon API wrapper.

API response structure (verified against live API):
  POST /search/     → {"docs": [...], "found": "1 - 10 of N", "categories": [...]}
  POST /doc/{tid}/  → {"tid", "title", "doc" (HTML), "numcitedby", ...}
  Citing cases      → POST /search/ with formInput "citedby:{tid}"

Each doc in search results has:
  tid, title, headline, fragment, citation, bench, publishdate, numcites, numcitedby

Without a token, all functions return mock dicts with a _note key.
"""
from __future__ import annotations

import requests

from core import config

_BASE = "https://api.indiankanoon.org"
_TIMEOUT = 10


def _headers() -> dict:
    if config.INDIAN_KANOON_API_TOKEN:
        return {"Authorization": f"Token {config.INDIAN_KANOON_API_TOKEN}"}
    return {}


def search(query: str, page: int = 0, doc_type: str = "") -> dict:
    """Search Indian Kanoon.

    Returns normalised dict: {"docs": [...], "found": str, "total_count": int}
    Each doc has: tid, title, headline, citation, bench, publishdate.
    """
    if not config.INDIAN_KANOON_API_TOKEN:
        return _mock_search(query)

    form_input = query
    if doc_type:
        form_input += f" doctypes:{doc_type}"

    try:
        r = requests.post(
            f"{_BASE}/search/",
            data={"formInput": form_input, "pagenum": page},
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        # Normalise: API returns "found": "1 - 10 of 6749"
        found_str = data.get("found", "0")
        try:
            total = int(found_str.split(" of ")[-1].replace(",", ""))
        except (ValueError, IndexError):
            total = len(data.get("docs", []))
        return {
            "docs": data.get("docs", []),
            "found": found_str,
            "total_count": total,
        }
    except requests.RequestException as e:
        return {"error": str(e), "docs": [], "found": "0", "total_count": 0}


def fetch_doc(tid: str | int) -> dict:
    """Fetch full document content by tid. Returns {"tid", "title", "doc" (HTML), ...}."""
    if not config.INDIAN_KANOON_API_TOKEN:
        return _mock_doc(tid)
    try:
        r = requests.post(
            f"{_BASE}/doc/{tid}/",
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        return {"error": str(e), "doc": "", "title": ""}


def citing_judgments(tid: str | int) -> dict:
    """Get judgments that cite a given document (by tid).

    Uses the citedby:{tid} search operator.
    Returns same structure as search().
    """
    if not config.INDIAN_KANOON_API_TOKEN:
        return _mock_citing(tid)
    return search(f"citedby:{tid}")


def _mock_search(query: str) -> dict:
    return {
        "docs": [],
        "found": "0",
        "total_count": 0,
        "_mock": True,
        "_note": (
            "Indian Kanoon API token not configured. "
            "Register at https://api.indiankanoon.org/ and set "
            "INDIAN_KANOON_API_TOKEN in your .env to enable live search."
        ),
    }


def _mock_doc(tid) -> dict:
    return {
        "tid": tid,
        "doc": f"[Mock] Document {tid} — configure INDIAN_KANOON_API_TOKEN for live data.",
        "title": "Mock Document",
        "_mock": True,
    }


def _mock_citing(tid) -> dict:
    return {
        "docs": [],
        "found": "0",
        "total_count": 0,
        "_mock": True,
        "_note": "Configure INDIAN_KANOON_API_TOKEN for live citation data.",
    }
