"""
Cliente mínimo PostgREST (Supabase) via HTTP assíncrono.
Requer: SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no ambiente.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Mapping, Optional, Union

import httpx

_log = logging.getLogger("analisadorcv")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _headers(prefer: Optional[str] = None) -> dict[str, str]:
    h = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


QueryParams = Optional[Union[Mapping[str, str], dict[str, str]]]


async def sb_request(
    method: str,
    path: str,
    *,
    params: QueryParams = None,
    json_body: Any = None,
    prefer: Optional[str] = None,
) -> httpx.Response:
    if not supabase_configured():
        raise RuntimeError("Supabase não configurado.")
    url = f"{SUPABASE_URL}/rest/v1/{path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        kw: dict[str, Any] = {"headers": _headers(prefer=prefer), "params": params}
        if json_body is not None:
            kw["json"] = json_body
        try:
            return await client.request(method, url, **kw)
        except httpx.RequestError as e:
            _log.warning("Supabase rede indisponível: %s %s — %s", method, path, e)
            raise


async def sb_json(method: str, path: str, **kwargs: Any) -> Any:
    r = await sb_request(method, path, **kwargs)
    if r.status_code >= 400:
        try:
            err = r.json()
            detail = err[0].get("message") if isinstance(err, list) and err else err
        except Exception:
            detail = r.text
        _log.warning("Supabase HTTP %s em %s %s: %s", r.status_code, method, path, detail)
        raise RuntimeError(f"Supabase HTTP {r.status_code}: {detail}")
    if not r.content.strip():
        return None
    return r.json()
