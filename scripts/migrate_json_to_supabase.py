#!/usr/bin/env python3
"""
Carga dos dados locais (JSON + pasta Historico) para o Supabase.

Pré-requisitos:
  - Tabelas criadas (supabase/migrations/001_initial.sql já executado).
  - .env na raiz do projeto com SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY.

Uso (na raiz do projeto):
  python scripts/migrate_json_to_supabase.py
  python scripts/migrate_json_to_supabase.py --dry-run
  python scripts/migrate_json_to_supabase.py --reset

--reset   Apaga todas as linhas das 4 tabelas (via API) e importa de novo.
--dry-run Apenas mostra o que seria importado, sem gravar.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = ROOT / "json"
HIST_DIR = ROOT / "Historico"
USERS_FILE = JSON_DIR / "users.json"
FEEDBACK_FILE = JSON_DIR / "artigos_feedback.json"
SUGESTOES_FILE = JSON_DIR / "sugestoes_funcionalidades.json"


def _env() -> tuple[str, str]:
    load_dotenv(ROOT / ".env")
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("Erro: defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no .env", file=sys.stderr)
        sys.exit(1)
    return url, key


def _headers(prefer: str | None = None) -> dict[str, str]:
    _, key = _env()
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _client() -> httpx.Client:
    """Todas as chamadas PostgREST precisam de apikey + Authorization (evita HTTP 401)."""
    url, _ = _env()
    return httpx.Client(
        base_url=f"{url}/rest/v1",
        timeout=120.0,
        headers=_headers(),
    )


def _raise_for_status(r: httpx.Response, ctx: str) -> None:
    if r.status_code >= 400:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise RuntimeError(f"{ctx}: HTTP {r.status_code} {detail}")


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8").strip() or "[]"
        data = json.loads(raw)
        return [x for x in data if isinstance(x, dict)]
    except Exception:
        return []


def _parse_ts(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    s = str(value).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        return s
    except ValueError:
        return None


def wipe_table(client: httpx.Client, table: str) -> int:
    """Remove todas as linhas (usa coluna id). Retorna quantidade apagada."""
    deleted = 0
    while True:
        r = client.get(table, params={"select": "id", "limit": "500"})
        _raise_for_status(r, f"GET {table}")
        rows = r.json()
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            rid = row.get("id")
            if not rid:
                continue
            d = client.delete(table, params={"id": f"eq.{rid}"})
            _raise_for_status(d, f"DELETE {table}")
            deleted += 1
    return deleted


def migrate_users(client: httpx.Client, dry: bool) -> int:
    rows = _load_json_list(USERS_FILE)
    n = 0
    for u in rows:
        username = str(u.get("username", "")).strip().lower()
        if not username:
            continue
        body = {
            "username": username,
            "salt": str(u.get("salt", "")),
            "password_hash": str(u.get("password_hash", "")),
        }
        ca = _parse_ts(str(u.get("created_at", "")))
        ua = _parse_ts(str(u.get("updated_at", "")))
        if ca:
            body["created_at"] = ca
        if ua:
            body["updated_at"] = ua
        if dry:
            print(f"  [user] {username}")
            n += 1
            continue
        r = client.get("app_users", params={"username": f"eq.{username}", "select": "username"})
        if r.status_code == 200 and isinstance(r.json(), list) and r.json():
            print(f"  [user] skip (já existe): {username}")
            continue
        ins = client.post("app_users", headers={**_headers(), "Prefer": "return=minimal"}, json=body)
        if ins.status_code == 409:
            print(f"  [user] skip (conflito): {username}")
            continue
        _raise_for_status(ins, f"POST app_users {username}")
        print(f"  [user] ok: {username}")
        n += 1
    return n


def migrate_historico(client: httpx.Client, dry: bool) -> int:
    if not HIST_DIR.exists():
        return 0
    files = sorted(HIST_DIR.glob("*.json"), reverse=True)
    n = 0
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [historico] skip arquivo inválido {path.name}: {e}")
            continue
        if not isinstance(data, dict):
            continue
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        usuario = str(meta.get("usuario", "")).strip().lower()
        if not usuario:
            print(f"  [historico] skip (sem meta.usuario): {path.name}")
            continue
        criado = _parse_ts(str(meta.get("data", ""))) or datetime.now().isoformat()
        body = {"usuario": usuario, "dados": data, "criado_em": criado}
        if dry:
            print(f"  [historico] {path.name} -> usuario={usuario}")
            n += 1
            continue
        ins = client.post("historico_analises", headers={**_headers(), "Prefer": "return=minimal"}, json=body)
        _raise_for_status(ins, f"POST historico {path.name}")
        print(f"  [historico] ok: {path.name} -> {usuario}")
        n += 1
    return n


def _valid_uuid(s: str) -> bool:
    try:
        uuid.UUID(str(s).strip())
        return True
    except Exception:
        return False


def migrate_feedback(client: httpx.Client, dry: bool) -> int:
    rows = _load_json_list(FEEDBACK_FILE)
    n = 0
    for row in rows:
        usuario = str(row.get("usuario", "")).strip().lower()
        nome = str(row.get("artigo_nome", "")).strip()
        if not usuario or not nome:
            continue
        body: dict[str, Any] = {
            "usuario": usuario,
            "analise_data": str(row.get("analise_data", "") or ""),
            "artigo_nome": nome,
            "artigo_link": str(row.get("artigo_link", "") or ""),
            "gostou": bool(row.get("gostou", False)),
        }
        ce = _parse_ts(str(row.get("criado_em", "")))
        if ce:
            body["criado_em"] = ce
        rid = str(row.get("id", "")).strip()
        if _valid_uuid(rid):
            body["id"] = rid
        if dry:
            print(f"  [feedback] {usuario} / {nome[:40]}...")
            n += 1
            continue
        ins = client.post("artigos_feedback", headers={**_headers(), "Prefer": "return=minimal"}, json=body)
        if ins.status_code == 409:
            print(f"  [feedback] skip (duplicado): {usuario} / {nome[:50]}")
            continue
        _raise_for_status(ins, "POST artigos_feedback")
        print(f"  [feedback] ok: {usuario} / {nome[:50]}")
        n += 1
    return n


def migrate_sugestoes(client: httpx.Client, dry: bool) -> int:
    rows = _load_json_list(SUGESTOES_FILE)
    n = 0
    for row in rows:
        usuario = str(row.get("usuario", "")).strip().lower()
        texto = str(row.get("sugestao", "")).strip()
        if not texto:
            continue
        body: dict[str, Any] = {"usuario": usuario or "unknown", "sugestao": texto}
        ce = _parse_ts(str(row.get("criado_em", "")))
        if ce:
            body["criado_em"] = ce
        rid = str(row.get("id", "")).strip()
        if _valid_uuid(rid):
            body["id"] = rid
        if dry:
            print(f"  [sugestao] {usuario}: {texto[:60]}...")
            n += 1
            continue
        ins = client.post("sugestoes_funcionalidades", headers={**_headers(), "Prefer": "return=minimal"}, json=body)
        _raise_for_status(ins, "POST sugestoes_funcionalidades")
        print(f"  [sugestao] ok")
        n += 1
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga JSON/Historico -> Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Não grava, só lista")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Apaga todas as linhas das tabelas (DELETE) antes de importar",
    )
    args = parser.parse_args()

    _env()
    dry = args.dry_run

    print(f"Raiz do projeto: {ROOT}")
    print(f"Usuários: {USERS_FILE} ({'existe' if USERS_FILE.exists() else 'ausente'})")
    print(f"Feedback: {FEEDBACK_FILE} ({'existe' if FEEDBACK_FILE.exists() else 'ausente'})")
    print(f"Sugestões: {SUGESTOES_FILE} ({'existe' if SUGESTOES_FILE.exists() else 'ausente'})")
    print(f"Histórico: {HIST_DIR} ({len(list(HIST_DIR.glob('*.json'))) if HIST_DIR.exists() else 0} arquivos .json)")

    if dry:
        print("\n--- DRY-RUN ---\n")

    with _client() as client:
        if args.reset and not dry:
            print("\n--reset: apagando dados existentes nas tabelas...")
            for tbl in ("sugestoes_funcionalidades", "artigos_feedback", "historico_analises", "app_users"):
                c = wipe_table(client, tbl)
                print(f"  apagados {c} registro(s) em {tbl}")
            print("")

        print("Importando usuários...")
        nu = migrate_users(client, dry)
        print(f"  total usuários processados: {nu}\n")

        print("Importando histórico (arquivos JSON)...")
        nh = migrate_historico(client, dry)
        print(f"  total análises: {nh}\n")

        print("Importando feedback de artigos...")
        nf = migrate_feedback(client, dry)
        print(f"  total feedbacks: {nf}\n")

        print("Importando sugestões...")
        ns = migrate_sugestoes(client, dry)
        print(f"  total sugestões: {ns}\n")

    if dry:
        print("Dry-run concluído. Execute sem --dry-run para gravar.")
    else:
        print("Carga concluída.")


if __name__ == "__main__":
    main()
