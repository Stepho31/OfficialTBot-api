from __future__ import annotations

import hashlib
from typing import Optional
import httpx

from app.settings import settings


def _get_datacenter(api_key: str) -> Optional[str]:
    """Extract the datacenter suffix from a Mailchimp API key."""
    if "-" not in api_key:
        return None
    return api_key.split("-")[-1]


async def _fetch_member_async(email: str) -> bool:
    """Async helper to check if a member exists on the Mailchimp list."""
    api_key = settings.MAILCHIMP_API_KEY
    list_id = settings.MAILCHIMP_LIST_ID
    if not api_key or not list_id:
        return False

    dc = _get_datacenter(api_key)
    if not dc:
        return False

    member_id = hashlib.md5(email.lower().encode("utf-8")).hexdigest()
    url = f"https://{dc}.api.mailchimp.com/3.0/lists/{list_id}/members/{member_id}"
    auth = httpx.BasicAuth("autopip", api_key)

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url, auth=auth)
        if resp.status_code != 200:
            return False
        status = resp.json().get("status")
        return status in {"subscribed", "pending"}
    except Exception:
        return False


def _fetch_member_sync(email: str) -> bool:
    """Synchronous fallback for when async is not needed."""
    api_key = settings.MAILCHIMP_API_KEY
    list_id = settings.MAILCHIMP_LIST_ID
    if not api_key or not list_id:
        return False

    dc = _get_datacenter(api_key)
    if not dc:
        return False

    member_id = hashlib.md5(email.lower().encode("utf-8")).hexdigest()
    url = f"https://{dc}.api.mailchimp.com/3.0/lists/{list_id}/members/{member_id}"
    auth = httpx.BasicAuth("autopip", api_key)

    try:
        resp = httpx.get(url, auth=auth, timeout=5)
        if resp.status_code != 200:
            return False
        status = resp.json().get("status")
        return status in {"subscribed", "pending"}
    except Exception:
        return False


async def is_on_waitlist_async(email: str) -> bool:
    """Public async API for Mailchimp lookup."""
    return await _fetch_member_async(email)


def is_on_waitlist(email: Optional[str]) -> bool:
    """Public sync API — safe to call in normal FastAPI endpoints."""
    if not email:
        return False
    return _fetch_member_sync(email)
