"""Indian Kanoon API client.

Without a token the client returns an empty result set plus a note, so the
tools stay usable and simply fall back to the model's own knowledge.
"""
from __future__ import annotations

import re
from typing import Any

import requests

from .. import settings
from ..llm import keyring

BASE_URL = "https://api.indiankanoon.org"
TIMEOUT = 20

NO_TOKEN_NOTE = (
    "Indian Kanoon search is not connected, so this answer comes from the model's own "
    "knowledge of Indian law. Add an Indian Kanoon token in Settings, or set "
    "INDIAN_KANOON_API_TOKEN on the server, to add live case retrieval."
)

_TAG_RE = re.compile(r"<[^>]+>")


def token() -> str:
    """The caller's own token if they supplied one, else the server's."""
    return keyring.kanoon_token() or (settings.INDIAN_KANOON_API_TOKEN or "")


def configured() -> bool:
    return bool(token())


def _headers() -> dict[str, str]:
    return {"Authorization": f"Token {token()}"}


def strip_html(value: Any) -> str:
    """Flatten a field from the API into clean plain text.

    Some fields, bench in particular, come back as a list of names rather than
    a string, so everything is normalised before the tags are stripped.
    """
    if value is None:
        text = ""
    elif isinstance(value, (list, tuple)):
        text = ", ".join(strip_html(item) for item in value if item)
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)
    text = _TAG_RE.sub(" ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text).strip()


def _empty(note: str) -> dict[str, Any]:
    return {"docs": [], "found": "0", "total_count": 0, "note": note, "connected": configured()}


def search(query: str, page: int = 0, doc_types: str = "") -> dict[str, Any]:
    """Search Indian Kanoon and return a normalised result payload."""
    if not configured():
        return _empty(NO_TOKEN_NOTE)

    form_input = query.strip()
    if doc_types:
        form_input = f"{form_input} doctypes:{doc_types}"

    try:
        response = requests.post(
            f"{BASE_URL}/search/",
            data={"formInput": form_input, "pagenum": page},
            headers=_headers(),
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.Timeout:
        return _empty("Indian Kanoon timed out. The answer below uses the model's knowledge only.")
    except requests.RequestException as exc:
        return _empty(f"Indian Kanoon could not be reached ({exc}). Answer is model knowledge only.")
    except ValueError:
        return _empty("Indian Kanoon returned an unexpected response. Answer is model knowledge only.")

    found = str(payload.get("found", "0"))
    try:
        total = int(found.split(" of ")[-1].replace(",", "").strip())
    except (ValueError, IndexError):
        total = len(payload.get("docs", []))

    docs = []
    for doc in payload.get("docs", []) or []:
        docs.append(
            {
                "tid": str(doc.get("tid", "")),
                "title": strip_html(doc.get("title", "")),
                "headline": strip_html(doc.get("headline") or doc.get("fragment") or ""),
                "citation": strip_html(doc.get("citation", "")),
                "bench": strip_html(doc.get("bench", "")),
                "court": strip_html(doc.get("docsource", "")),
                "date": doc.get("publishdate", ""),
                "url": f"https://indiankanoon.org/doc/{doc.get('tid', '')}/" if doc.get("tid") else "",
            }
        )

    return {"docs": docs, "found": found, "total_count": total, "note": "", "connected": True}


def fetch_doc(tid: str | int) -> dict[str, Any]:
    if not configured():
        return {"tid": str(tid), "title": "", "text": "", "note": NO_TOKEN_NOTE}
    try:
        response = requests.post(f"{BASE_URL}/doc/{tid}/", headers=_headers(), timeout=TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {"tid": str(tid), "title": "", "text": "", "note": f"Could not fetch document: {exc}"}
    return {
        "tid": str(payload.get("tid", tid)),
        "title": strip_html(payload.get("title", "")),
        "text": strip_html(payload.get("doc", "")),
        "note": "",
    }


def citing_judgments(tid: str | int) -> dict[str, Any]:
    if not configured():
        return _empty(NO_TOKEN_NOTE)
    return search(f"citedby:{tid}")
