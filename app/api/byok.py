"""Bring your own key: read a request's credentials out of its headers.

`bind_client_keys` is attached once, to the whole /api router, so every tool
endpoint picks up the caller's keys without a single handler having to know
that the feature exists. The credentials live in a context variable for the
duration of the request and are dropped when it ends.

Nothing here logs a header value, and no key is ever written to the database
or returned in a response body.
"""
from __future__ import annotations

from fastapi import Request

from .. import settings
from ..llm import keyring

# Slugs a client is allowed to send a credential for. An unknown slug is
# ignored rather than forwarded anywhere.
ALLOWED_SLUGS = frozenset(
    {"gemini", "groq", "cloudflare", "openai", "huggingface", keyring.KANOON_SLUG}
)

# Only gateways that speak the OpenAI protocol accept a base URL override.
ALLOWED_BASE_URL_SLUGS = frozenset({"openai", "huggingface", "groq"})

# Providers that need a second value alongside the key. Cloudflare puts the
# account id in the request URL, so a token on its own addresses nothing.
ALLOWED_ACCOUNT_SLUGS = frozenset({"cloudflare"})


async def bind_client_keys(request: Request) -> None:
    if not settings.ALLOW_CLIENT_KEYS:
        keyring.reset()
        return

    keys: dict[str, str] = {}
    base_urls: dict[str, str] = {}
    accounts: dict[str, str] = {}

    for raw_name, raw_value in request.headers.items():
        name = raw_name.lower()
        if name.startswith(keyring.KEY_PREFIX):
            slug = name[len(keyring.KEY_PREFIX) :]
            if slug in ALLOWED_SLUGS:
                cleaned = keyring.clean_key(raw_value)
                if cleaned:
                    keys[slug] = cleaned
        elif name.startswith(keyring.ACCOUNT_PREFIX):
            slug = name[len(keyring.ACCOUNT_PREFIX) :]
            if slug in ALLOWED_ACCOUNT_SLUGS:
                cleaned = keyring.clean_account(raw_value)
                if cleaned:
                    accounts[slug] = cleaned
        elif name.startswith(keyring.BASE_URL_PREFIX):
            slug = name[len(keyring.BASE_URL_PREFIX) :]
            if slug in ALLOWED_BASE_URL_SLUGS:
                cleaned = keyring.clean_base_url(raw_value)
                if cleaned:
                    base_urls[slug] = cleaned

    keyring.bind(keys, base_urls, accounts)
