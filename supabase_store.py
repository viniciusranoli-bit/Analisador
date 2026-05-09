"""
Persistência no Supabase (PostgREST). Usado quando SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY estão definidos.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from supabase_client import supabase_configured, sb_json


def _norm_user(u: str) -> str:
    return str(u or "").strip().lower()


async def db_users_list() -> list[dict[str, Any]]:
    rows = await sb_json("GET", "app_users", params={"select": "username,email,role,created_at,updated_at", "order": "username.asc"})
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append({
                "username": str(r.get("username", "")),
                "email": str(r.get("email", "")),
                "role": str(r.get("role", "user")),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            })
    return out


async def db_users_find_by_username(username: str) -> Optional[dict[str, Any]]:
    u = _norm_user(username)
    if not u:
        return None
    rows = await sb_json(
        "GET",
        "app_users",
        params={"select": "*", "username": f"eq.{u}", "limit": "1"},
    )
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return None


async def db_users_find_by_email(email: str) -> Optional[dict[str, Any]]:
    e = _norm_user(email)
    if not e:
        return None
    rows = await sb_json(
        "GET",
        "app_users",
        params={"select": "*", "email": f"eq.{e}", "limit": "1"},
    )
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return None


async def db_users_find(username: str) -> Optional[dict[str, Any]]:
    return await db_users_find_by_username(username)


async def db_users_insert(username: str, email: str, salt: str, password_hash: str, role: str = "user") -> None:
    u = _norm_user(username)
    e = _norm_user(email)
    r = role if role in ("admin", "user") else "user"
    now = datetime.now().isoformat()
    await sb_json(
        "POST",
        "app_users",
        json_body={"username": u, "email": e, "role": r, "salt": salt, "password_hash": password_hash, "created_at": now, "updated_at": now},
        prefer="return=minimal",
    )


async def db_users_update(username_old: str, new_username: Optional[str], new_email: Optional[str], password_hash: Optional[str], salt: Optional[str], new_role: Optional[str] = None) -> bool:
    old = _norm_user(username_old)
    patch: dict[str, Any] = {"updated_at": datetime.now().isoformat()}
    if new_username:
        patch["username"] = _norm_user(new_username)
    if new_email:
        patch["email"] = _norm_user(new_email)
    if new_role and new_role in ("admin", "user"):
        patch["role"] = new_role
    if password_hash and salt:
        patch["password_hash"] = password_hash
        patch["salt"] = salt
    rows = await sb_json(
        "PATCH",
        "app_users",
        params={"username": f"eq.{old}"},
        json_body=patch,
        prefer="return=representation",
    )
    return bool(isinstance(rows, list) and rows)


async def db_users_delete(username: str) -> bool:
    u = _norm_user(username)
    rows = await sb_json(
        "DELETE",
        "app_users",
        params={"username": f"eq.{u}", "select": "id"},
        prefer="return=representation",
    )
    return bool(isinstance(rows, list) and rows)


async def db_historico_insert(usuario: str, payload: dict[str, Any]) -> str:
    u = _norm_user(usuario)
    row = await sb_json(
        "POST",
        "historico_analises",
        json_body={"usuario": u, "dados": payload},
        prefer="return=representation",
    )
    if isinstance(row, list) and row and isinstance(row[0], dict):
        return str(row[0].get("id", ""))
    raise RuntimeError("Falha ao inserir histórico no Supabase.")


async def db_historico_list(usuario: str) -> list[dict[str, Any]]:
    u = _norm_user(usuario)
    rows = await sb_json(
        "GET",
        "historico_analises",
        params={
            "select": "id,dados,criado_em",
            "usuario": f"eq.{u}",
            "order": "criado_em.desc",
        },
    )
    if not isinstance(rows, list):
        return []
    itens = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        data = r.get("dados") or {}
        if not isinstance(data, dict):
            data = {}
        meta = data.get("meta", {}) if isinstance(data.get("meta"), dict) else {}
        itens.append({
            "arquivo": str(r.get("id", "")),
            "data": meta.get("data", "") or r.get("criado_em", ""),
            "score": data.get("score", 0),
            "especialidade": meta.get("especialidade", ""),
            "senioridade": meta.get("senioridade", ""),
            "objetivo": meta.get("objetivo", ""),
            "veredito": data.get("veredito", ""),
            "resumo_executivo": data.get("resumo_executivo", ""),
        })
    return itens


async def db_historico_get(arquivo_id: str, usuario: str) -> Optional[dict[str, Any]]:
    u = _norm_user(usuario)
    aid = str(arquivo_id or "").strip()
    if not aid:
        return None
    rows = await sb_json(
        "GET",
        "historico_analises",
        params={"select": "dados,usuario", "id": f"eq.{aid}", "limit": "1"},
    )
    if not (isinstance(rows, list) and rows and isinstance(rows[0], dict)):
        return None
    row = rows[0]
    if _norm_user(str(row.get("usuario", ""))) != u:
        return None
    dados = row.get("dados")
    return dados if isinstance(dados, dict) else None


async def db_feedback_list(usuario: str, analise_data: str) -> list[dict[str, Any]]:
    u = _norm_user(usuario)
    params: dict[str, str] = {
        "select": "*",
        "usuario": f"eq.{u}",
        "order": "criado_em.desc",
    }
    ad = str(analise_data or "").strip()
    if ad:
        params["analise_data"] = f"eq.{ad}"
    rows = await sb_json("GET", "artigos_feedback", params=params)
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append({
                "id": str(r.get("id", "")),
                "usuario": r.get("usuario"),
                "analise_data": r.get("analise_data", ""),
                "artigo_nome": r.get("artigo_nome", ""),
                "artigo_link": r.get("artigo_link", ""),
                "gostou": bool(r.get("gostou", False)),
                "criado_em": r.get("criado_em", ""),
            })
    return out


async def db_feedback_upsert(
    usuario: str,
    analise_data: str,
    artigo_nome: str,
    artigo_link: str,
    gostou: bool,
) -> tuple[bool, str]:
    """Retorna (updated, id)."""
    u = _norm_user(usuario)
    nome = str(artigo_nome or "").strip()
    ad = str(analise_data or "").strip()
    qparams: dict[str, str] = {"select": "id,artigo_nome,analise_data", "usuario": f"eq.{u}"}
    if ad:
        qparams["analise_data"] = f"eq.{ad}"
    existing = await sb_json("GET", "artigos_feedback", params=qparams)
    row_id: Optional[str] = None
    if isinstance(existing, list):
        for row in existing:
            if not isinstance(row, dict):
                continue
            if str(row.get("analise_data", "")).strip() != ad:
                continue
            if str(row.get("artigo_nome", "")).strip().lower() == nome.lower():
                row_id = str(row.get("id", ""))
                break
    now_iso = datetime.now().isoformat()
    if row_id:
        await sb_json(
            "PATCH",
            "artigos_feedback",
            params={"id": f"eq.{row_id}"},
            json_body={
                "artigo_link": artigo_link,
                "gostou": gostou,
                "criado_em": now_iso,
            },
            prefer="return=minimal",
        )
        return True, row_id
    new_id = str(uuid.uuid4())
    await sb_json(
        "POST",
        "artigos_feedback",
        json_body={
            "id": new_id,
            "usuario": u,
            "analise_data": ad,
            "artigo_nome": nome,
            "artigo_link": artigo_link,
            "gostou": gostou,
            "criado_em": now_iso,
        },
        prefer="return=minimal",
    )
    return False, new_id


async def db_sugestao_insert(usuario: str, texto: str) -> None:
    u = _norm_user(usuario)
    await sb_json(
        "POST",
        "sugestoes_funcionalidades",
        json_body={
            "id": str(uuid.uuid4()),
            "usuario": u,
            "sugestao": texto,
            "criado_em": datetime.now().isoformat(),
        },
        prefer="return=minimal",
    )


async def db_feedback_all() -> list[dict[str, Any]]:
    rows = await sb_json("GET", "artigos_feedback", params={"select": "*", "order": "criado_em.asc"})
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


async def db_sugestoes_all() -> list[dict[str, Any]]:
    rows = await sb_json("GET", "sugestoes_funcionalidades", params={"select": "*", "order": "criado_em.desc"})
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


async def db_historico_usuarios_for_stats() -> list[str]:
    """Um valor `usuario` por linha de histórico (para totais e agregação no admin)."""
    rows = await sb_json(
        "GET",
        "historico_analises",
        params={"select": "usuario"},
    )
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    for r in rows:
        if isinstance(r, dict):
            u = str(r.get("usuario", "")).strip().lower()
            if u:
                out.append(u)
    return out
